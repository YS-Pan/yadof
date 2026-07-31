"""Checkpoint discovery, loading, and surrogate inference."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import threading
from typing import Mapping, Sequence

import numpy as np
import torch

from yadof.config import load_config
from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_contract import RawDataView
from yadof.surrogate.modeling import (
    load_inr_artifacts,
    predict_conditional_inr_members,
)
from yadof.surrogate.runtime import (
    _interpolate_regular_grid,
    _raw_samples_from_flat,
    predict_rawdata_slot_members_at_coordinates,
)
from yadof.surrogate.types import RawArraySlot, RawDataSchema, TargetScaler

from .rawdata import (
    copy_template,
    plot_from_coordinate_grid,
    rawdata_dimensions,
    summarize_errors_by_item,
)
from .types import (
    CheckpointInfo,
    PlotData,
    PlotRequest,
    ProgressCallback,
    _check_cancelled,
)


def discover_checkpoints(
    checkpoint_dir: Path,
) -> tuple[CheckpointInfo, ...]:
    """Return valid checkpoint descriptors in increasing generation order."""

    checkpoints: list[CheckpointInfo] = []
    for path in sorted(Path(checkpoint_dir).glob("generation_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            generation = int(payload["generation_index"])
            sample_count = int(payload.get("sample_count", 0))
            train_history = payload.get("train_history", {})
            member_count = int(
                payload.get(
                    "member_count",
                    dict(train_history).get("member_count", 1),
                )
            )
            schema = payload.get("schema", {})
            flat_dim = (
                int(dict(schema).get("flat_dim", 0))
                if isinstance(schema, Mapping)
                else 0
            )
            skipped = bool(
                dict(train_history).get("skipped", False)
                if isinstance(train_history, Mapping)
                else False
            )
            if member_count <= 0 or flat_dim <= 0 or skipped:
                continue
            raw_error = payload.get("mean_relative_error")
            training_error = (
                float(raw_error)
                if raw_error is not None and math.isfinite(float(raw_error))
                else None
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        checkpoints.append(
            CheckpointInfo(
                generation=generation,
                path=path.resolve(),
                sample_count=sample_count,
                member_count=member_count,
                training_error=training_error,
                payload=payload,
            )
        )
    return tuple(sorted(checkpoints, key=lambda item: item.generation))


def _select_device(config) -> torch.device:
    requested = str(getattr(config, "SURROGATE_TORCH_DEVICE", "auto")).lower()
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return torch.device("xpu")
    return torch.device("cpu")


@dataclass(frozen=True)
class _CheckpointAuditPrediction:
    costs: tuple[tuple[float, ...], ...]
    raw_relative_sums: np.ndarray
    raw_relative_counts: np.ndarray
    raw_absolute_sums: np.ndarray
    raw_absolute_counts: np.ndarray


class CheckpointPredictor:
    """One loaded checkpoint with batched rawData and objective prediction."""

    def __init__(
        self,
        workspace: Path,
        checkpoint: CheckpointInfo,
        template_sample: Sequence[Mapping[str, object]],
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.checkpoint = checkpoint
        self._config = load_config(self.workspace)
        self.device = _select_device(self._config)
        payload = checkpoint.payload

        artifact_name = Path(
            str(
                payload.get(
                    "artifact_dir",
                    f"generation_{checkpoint.generation:04d}_conditional_inr",
                )
            )
        ).name
        self.artifact_dir = checkpoint.path.parent / artifact_name
        model_name = Path(str(payload.get("model_path", "model_aux.npz"))).name
        auxiliary_path = self.artifact_dir / model_name
        if not auxiliary_path.is_file():
            raise FileNotFoundError(auxiliary_path)

        checkpoint_names = tuple(str(value) for value in payload["parameter_names"])
        current_names = job_template_api.get_parameter_names(self.workspace)
        if checkpoint_names != current_names:
            raise ValueError(
                "checkpoint parameters do not match the current workspace task"
            )
        self.parameter_names = current_names

        schema_payload = payload.get("schema")
        if not isinstance(schema_payload, Mapping):
            raise ValueError("checkpoint is missing rawData schema")
        raw_slots = schema_payload.get("modeled_slots")
        if not isinstance(raw_slots, Sequence):
            raise ValueError("checkpoint is missing modeled rawData slots")
        slots = tuple(
            RawArraySlot(
                item_index=int(dict(slot)["item_index"]),
                key=str(dict(slot)["key"]),
                shape=tuple(int(value) for value in dict(slot)["shape"]),
                dtype=str(dict(slot)["dtype"]),
                start=int(dict(slot)["start"]),
                end=int(dict(slot)["end"]),
                field_id=int(dict(slot)["field_id"]),
            )
            for slot in raw_slots
        )
        flat_dim = int(schema_payload["flat_dim"])
        templates = copy_template(template_sample)
        expected_items = int(
            schema_payload.get("rawdata_item_count", len(templates))
        )
        if len(templates) != expected_items:
            raise ValueError(
                f"checkpoint expects {expected_items} rawData items, "
                f"got {len(templates)}"
            )
        for slot in slots:
            if slot.item_index >= len(templates):
                raise ValueError("checkpoint rawData slot references a missing item")
            actual = np.asarray(templates[slot.item_index][slot.key]).shape
            if tuple(actual) != slot.shape:
                raise ValueError(
                    f"checkpoint rawData shape mismatch for item {slot.item_index}: "
                    f"{tuple(actual)} != {slot.shape}"
                )

        with np.load(auxiliary_path, allow_pickle=False) as auxiliary:
            target_mean = np.asarray(auxiliary["target_mean"], dtype=np.float32)
            target_scale = np.asarray(auxiliary["target_scale"], dtype=np.float32)
            coord_table = np.asarray(auxiliary["coord_table"], dtype=np.float32)
            field_ids = np.asarray(auxiliary["field_ids"], dtype=np.int64)
        if target_mean.size != flat_dim or target_scale.size != flat_dim:
            raise ValueError("checkpoint target scaler does not match rawData schema")
        if coord_table.shape[0] != flat_dim or field_ids.size != flat_dim:
            raise ValueError("checkpoint query table does not match rawData schema")

        self.schema = RawDataSchema(
            templates=templates,
            modeled_slots=slots,
            flat_dim=flat_dim,
            coord_table=np.ascontiguousarray(coord_table, dtype=np.float32),
            field_ids=np.ascontiguousarray(field_ids, dtype=np.int64),
        )
        self.scaler = TargetScaler(
            mean=np.ascontiguousarray(target_mean, dtype=np.float32),
            scale=np.ascontiguousarray(target_scale, dtype=np.float32),
        )
        self.model, input_dim, n_fields, self.train_cfg = load_inr_artifacts(
            self.artifact_dir,
            self.device,
        )
        if int(input_dim) != len(self.parameter_names):
            raise ValueError("checkpoint model input width does not match parameters")
        if int(n_fields) != self.schema.n_fields:
            raise ValueError("checkpoint model fields do not match rawData schema")

    def _predict_member_flats(
        self,
        normalized_rows: Sequence[Sequence[float]],
        *,
        sample_batch: int | None = None,
    ) -> np.ndarray:
        matrix = np.asarray(normalized_rows, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix[None, :]
        if matrix.ndim != 2 or matrix.shape[1] != len(self.parameter_names):
            raise ValueError(
                f"expected normalized values with width "
                f"{len(self.parameter_names)}"
            )
        matrix = np.ascontiguousarray(
            np.clip(matrix, 0.0, 1.0),
            dtype=np.float32,
        )
        configured_batch = max(1, int(self.train_cfg.sample_batch_eval))
        requested_batch = (
            configured_batch if sample_batch is None else max(1, int(sample_batch))
        )
        current_batch = min(requested_batch, len(matrix))
        while True:
            try:
                scaled = predict_conditional_inr_members(
                    model=self.model,
                    X=matrix,
                    coord_table=self.schema.coord_table,
                    field_ids=self.schema.field_ids,
                    device=self.device,
                    sample_batch=current_batch,
                    query_batch=max(1, int(self.train_cfg.query_batch_eval)),
                )
                break
            except torch.OutOfMemoryError:
                if self.device.type != "cuda" or current_batch <= configured_batch:
                    raise
                current_batch = max(configured_batch, current_batch // 2)
                torch.cuda.empty_cache()
        return self.scaler.inverse_members(scaled)

    def predict(
        self,
        normalized_rows: Sequence[Sequence[float]],
        *,
        include_members: bool = False,
    ) -> tuple[
        tuple[tuple[Mapping[str, object], ...], ...],
        tuple[tuple[float, ...], ...],
        tuple[tuple[tuple[Mapping[str, object], ...], ...], ...],
    ]:
        rows = tuple(
            tuple(float(value) for value in row)
            for row in normalized_rows
        )
        if not rows:
            return (), (), ()
        member_flats = self._predict_member_flats(rows)
        mean_samples = _raw_samples_from_flat(
            self.schema,
            np.mean(member_flats, axis=0),
        )
        raw_rows = tuple(
            job_template_api.denormalize_variables(self.workspace, row)
            for row in rows
        )
        costs = job_template_api.calculate_cost(
            self.workspace,
            mean_samples,
            raw_variables=raw_rows,
        )
        if not include_members:
            return mean_samples, costs, ()
        member_samples = tuple(
            _raw_samples_from_flat(self.schema, member_flat)
            for member_flat in member_flats
        )
        return mean_samples, costs, member_samples

    def predict_plot(
        self,
        normalized_rows: Sequence[Sequence[float]],
        request: PlotRequest,
    ) -> tuple[PlotData, tuple[PlotData, ...]]:
        """Predict one plotted slice at physical, possibly off-grid coordinates."""

        item_index = int(request.item_index)
        if not 0 <= item_index < len(self.schema.templates):
            raise IndexError(item_index)
        template = self.schema.templates[item_index]
        view = RawDataView.from_item(template)
        dimensions = rawdata_dimensions(self.schema.templates, item_index)
        selected = tuple(int(value) for value in request.plotted_dimensions)
        if len(selected) > 2 or len(set(selected)) != len(selected):
            raise ValueError("choose zero, one, or two unique plot dimensions")
        if any(index < 0 or index >= len(dimensions) for index in selected):
            raise IndexError("plot dimension is outside the rawData rank")
        fixed = request.fixed_map
        if any(
            dimension.index not in selected
            and dimension.index not in fixed
            for dimension in dimensions
        ):
            raise ValueError("every unplotted dimension needs a fixed value")

        targets = tuple(
            (
                np.asarray(dimension.coordinates, dtype=np.float64)
                if dimension.index in selected
                else np.asarray([fixed[dimension.index]], dtype=np.float64)
            )
            for dimension in dimensions
        )
        modeled = any(
            slot.item_index == item_index and slot.key == view.data_key
            for slot in self.schema.modeled_slots
        )
        if modeled:
            member_values = predict_rawdata_slot_members_at_coordinates(
                model=self.model,
                schema=self.schema,
                scaler=self.scaler,
                train_cfg=self.train_cfg,
                device=self.device,
                normalized_rows=normalized_rows,
                item_index=item_index,
                key=view.data_key,
                axis_coordinates=targets,
            )
            if member_values.shape[1] != 1:
                raise ValueError("viewer plot prediction expects one parameter row")
            grids = np.asarray(member_values[:, 0], dtype=np.float64)
        else:
            source_axes = tuple(
                np.asarray(dimension.coordinates, dtype=np.float64)
                for dimension in dimensions
            )
            constant_grid = _interpolate_regular_grid(
                np.real(np.asarray(view.data)).astype(
                    np.float64,
                    copy=False,
                ),
                source_axes,
                targets,
            )
            grids = np.repeat(
                constant_grid[None, ...],
                max(1, int(self.checkpoint.member_count)),
                axis=0,
            )

        name = view.name or f"rawData {item_index}"
        mean_plot = plot_from_coordinate_grid(
            name=name,
            dimensions=dimensions,
            values=np.mean(grids, axis=0, dtype=np.float64),
            plotted_dimensions=selected,
            fixed_values=fixed,
        )
        member_plots = tuple(
            plot_from_coordinate_grid(
                name=name,
                dimensions=dimensions,
                values=values,
                plotted_dimensions=selected,
                fixed_values=fixed,
            )
            for values in grids
        )
        return mean_plot, member_plots

    def predict_audit_rows(
        self,
        normalized_rows: Sequence[Sequence[float]],
        true_flats: np.ndarray,
        *,
        relative_epsilon: float,
        batch_size: int = 512,
        cuda_sample_batch: int = 128,
        cancel_event: threading.Event | None = None,
        progress: ProgressCallback | None = None,
        progress_offset: int = 0,
        progress_total: int | None = None,
    ) -> _CheckpointAuditPrediction:
        """Predict costs and per-rawData errors without retaining predictions."""

        rows = tuple(
            tuple(float(value) for value in row)
            for row in normalized_rows
        )
        true_flats = np.ascontiguousarray(true_flats, dtype=np.float64)
        if true_flats.shape != (len(rows), int(self.schema.flat_dim)):
            raise ValueError(
                "true rawData matrix does not match checkpoint prediction dimensions"
            )

        raw_shape = (len(rows), len(self.schema.templates))
        output_costs: list[tuple[float, ...]] = []
        raw_relative_sums = np.zeros(raw_shape, dtype=np.float64)
        raw_relative_counts = np.zeros(raw_shape, dtype=np.int64)
        raw_absolute_sums = np.zeros(raw_shape, dtype=np.float64)
        raw_absolute_counts = np.zeros(raw_shape, dtype=np.int64)
        size = max(1, int(batch_size))
        total = len(rows) if progress_total is None else int(progress_total)
        accelerated_sample_batch = (
            max(int(self.train_cfg.sample_batch_eval), int(cuda_sample_batch))
            if self.device.type == "cuda"
            else int(self.train_cfg.sample_batch_eval)
        )

        for start in range(0, len(rows), size):
            _check_cancelled(cancel_event)
            batch = rows[start : start + size]
            member_flats = self._predict_member_flats(
                batch,
                sample_batch=accelerated_sample_batch,
            )
            mean_flats = np.mean(member_flats, axis=0, dtype=np.float64)
            del member_flats
            _check_cancelled(cancel_event)

            true_batch = true_flats[start : start + len(batch)]
            absolute = np.abs(mean_flats - true_batch)
            relative = absolute / np.maximum(
                np.abs(true_batch),
                float(relative_epsilon),
            )
            row_slice = slice(start, start + len(batch))
            (
                raw_absolute_sums[row_slice],
                raw_absolute_counts[row_slice],
            ) = summarize_errors_by_item(self.schema, absolute)
            (
                raw_relative_sums[row_slice],
                raw_relative_counts[row_slice],
            ) = summarize_errors_by_item(self.schema, relative)

            mean_samples = _raw_samples_from_flat(self.schema, mean_flats)
            raw_rows = tuple(
                job_template_api.denormalize_variables(self.workspace, row)
                for row in batch
            )
            costs = job_template_api.calculate_cost(
                self.workspace,
                mean_samples,
                raw_variables=raw_rows,
            )
            output_costs.extend(
                tuple(float(value) for value in row)
                for row in costs
            )
            if progress is not None:
                completed = min(start + len(batch), len(rows))
                progress(
                    progress_offset + completed,
                    total,
                    f"Checkpoint {self.checkpoint.generation}: "
                    f"{completed}/{len(rows)} · inference batch "
                    f"{accelerated_sample_batch}",
                )

        _check_cancelled(cancel_event)
        return _CheckpointAuditPrediction(
            costs=tuple(output_costs),
            raw_relative_sums=raw_relative_sums,
            raw_relative_counts=raw_relative_counts,
            raw_absolute_sums=raw_absolute_sums,
            raw_absolute_counts=raw_absolute_counts,
        )
