"""Read-only viewer adapter for hierarchical-CAE checkpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import threading
from typing import Mapping, Sequence

import numpy as np
import torch

from yadof.config import load_config
from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_contract import RawDataView
from yadof.surrogate.conditional_inr.types import RawArraySlot, RawDataSchema
from yadof.surrogate.hierarchical_cae.checkpoints import (
    COMPONENT_NAMESPACE,
    resolve_artifact_dir,
    resolve_namespace_manifest_path,
    run_namespace_for_signature,
    schema_payload,
    semantic_state_signature,
    validate_manifest_identity,
)
from yadof.surrogate.hierarchical_cae.coordinates import (
    coordinate_grid,
    interpolate_stored_values,
)
from yadof.surrogate.hierarchical_cae.modeling import (
    load_model_bundle,
    predict_hierarchical_coordinate_members,
    predict_hierarchical_members,
)
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    named_sample_from_payloads,
)
from yadof.surrogate.hierarchical_cae.types import FieldScaler
from yadof.surrogate.quality import quality_policy_from_mapping

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


def _json_normalized_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(dict(value), sort_keys=True))


def discover_hierarchical_cae_checkpoints(
    checkpoint_dir: Path,
    *,
    parameter_definition_signature: Mapping[str, object] | None = None,
    strategy_signature: str | None = None,
) -> tuple[CheckpointInfo, ...]:
    """Discover validated coordinate/full-grid hierarchical checkpoints."""

    compatible_parameter_signature = (
        None
        if parameter_definition_signature is None
        else _json_normalized_mapping(parameter_definition_signature)
    )
    run_pattern = (
        "*"
        if strategy_signature is None
        else run_namespace_for_signature(strategy_signature)
    )
    selected: dict[tuple[str, int], CheckpointInfo] = {}
    paths = Path(checkpoint_dir).glob(
        f"runs/{run_pattern}/components/{COMPONENT_NAMESPACE}/generation_*.json"
    )
    for path in sorted(paths):
        try:
            payload = validate_manifest_identity(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if strategy_signature is not None and str(
                payload["strategy_signature"]
            ) != str(strategy_signature):
                continue
            if (
                compatible_parameter_signature is not None
                and payload["parameter_definition_signature"]
                != compatible_parameter_signature
            ):
                continue
            generation = int(payload["generation_index"])
            member_count = int(payload["member_count"])
            schema = payload["schema"]
            flat_dim = (
                int(dict(schema).get("flat_dim", 0))
                if isinstance(schema, Mapping)
                else 0
            )
            history = payload["train_history"]
            skipped = bool(
                dict(history).get("skipped", False)
                if isinstance(history, Mapping)
                else False
            )
            namespace_manifest = resolve_namespace_manifest_path(
                Path(checkpoint_dir), payload
            )
            artifact_dir = resolve_artifact_dir(Path(checkpoint_dir), payload)
            model_path = artifact_dir / Path(str(payload["model_path"])).name
            scaler_path = artifact_dir / Path(str(payload["scaler_path"])).name
            if (
                member_count <= 0
                or flat_dim <= 0
                or skipped
                or namespace_manifest.resolve() != path.resolve()
                or not model_path.is_file()
                or not scaler_path.is_file()
            ):
                continue
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        candidate = CheckpointInfo(
            generation=generation,
            path=path.resolve(),
            sample_count=int(payload["sample_count"]),
            member_count=member_count,
            payload=payload,
        )
        key = (str(payload["run_namespace"]), generation)
        previous = selected.get(key)
        if previous is None or str(payload["publication_id"]) > str(
            previous.payload["publication_id"]
        ):
            selected[key] = candidate
    return tuple(
        selected[key]
        for key in sorted(selected, key=lambda item: (item[1], item[0]))
    )


def _select_device() -> torch.device:
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


class HierarchicalCAECheckpointPredictor:
    """Validated full-grid plus coordinate readout for one checkpoint."""

    def __init__(
        self,
        workspace: Path,
        checkpoint: CheckpointInfo,
        template_sample: Sequence[Mapping[str, object]],
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.checkpoint = checkpoint
        self._config = load_config(self.workspace)
        self.device = _select_device()
        payload = validate_manifest_identity(checkpoint.payload)
        self.artifact_dir = resolve_artifact_dir(
            self._config.workspace.surrogate_checkpoint_dir, payload
        )
        checkpoint_names = tuple(str(value) for value in payload["parameter_names"])
        current_names = job_template_api.get_parameter_names(self.workspace)
        if checkpoint_names != current_names:
            raise ValueError(
                "checkpoint parameters do not match the current workspace task"
            )
        current_parameter_signature = _json_normalized_mapping(
            job_template_api.get_parameter_definition_signature(self.workspace)
        )
        if payload["parameter_definition_signature"] != current_parameter_signature:
            raise ValueError(
                "checkpoint parameter normalization does not match the current workspace"
            )
        self.parameter_names = current_names

        raw_schema = payload.get("schema")
        if not isinstance(raw_schema, Mapping):
            raise ValueError("checkpoint is missing hierarchical rawData schema")
        slots_payload = raw_schema.get("modeled_slots")
        layouts_payload = raw_schema.get("layouts")
        if not isinstance(slots_payload, Sequence) or not isinstance(
            layouts_payload, Sequence
        ):
            raise ValueError("checkpoint hierarchical schema is incomplete")
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
            for slot in slots_payload
        )
        templates = copy_template(template_sample)
        if len(templates) != len(slots):
            raise ValueError(
                "hierarchical checkpoint expects exactly one modeled field per rawData item"
            )
        filenames = tuple(
            str(dict(slot)["selector"][0])
            for slot in sorted(slots_payload, key=lambda item: int(dict(item)["item_index"]))
        )
        named_template = named_sample_from_payloads(filenames, templates)
        field_layouts = {}
        axis_encodings = {}
        for raw_layout in layouts_payload:
            layout = dict(raw_layout)
            selector = tuple(str(value) for value in layout["selector"])
            if len(layout["shape"]) == 3:
                field_layouts[selector] = {
                    "channel_axes": tuple(layout["channel_axes"]),
                    "spatial_axes": tuple(layout["spatial_axes"]),
                }
            axis_encodings[selector] = {
                str(name): dict(encoding)
                for name, encoding in zip(
                    layout["axis_names"], layout["axis_encodings"]
                )
            }
        groups = tuple(
            tuple(tuple(str(value) for value in selector) for selector in group)
            for group in raw_schema.get("groups", ())
        )
        hierarchical_schema = build_schema(
            named_template,
            groups=groups,
            field_layouts=field_layouts,
            axis_encodings=axis_encodings,
        )
        if schema_payload(hierarchical_schema) != dict(raw_schema):
            raise ValueError(
                "checkpoint rawData schema does not match the current viewer template"
            )
        scaler_path = self.artifact_dir / Path(str(payload["scaler_path"])).name
        scalers = []
        with np.load(scaler_path, allow_pickle=False) as stored:
            for field_index, layout in enumerate(hierarchical_schema.layouts):
                mean = np.asarray(
                    stored[f"field_{field_index:04d}_mean"], dtype=np.float64
                )
                scale = np.asarray(
                    stored[f"field_{field_index:04d}_scale"], dtype=np.float64
                )
                if (
                    mean.size != layout.point_count
                    or scale.size != layout.point_count
                    or not np.all(np.isfinite(mean))
                    or not np.all(np.isfinite(scale))
                    or np.any(scale <= 0)
                ):
                    raise ValueError("checkpoint field scaler is invalid")
                scalers.append(
                    FieldScaler(
                        np.ascontiguousarray(mean), np.ascontiguousarray(scale)
                    )
                )
        self.hierarchical_schema = replace(
            hierarchical_schema, scalers=tuple(scalers)
        )
        flat_dim = int(raw_schema["flat_dim"])
        self.schema = RawDataSchema(
            templates=templates,
            modeled_slots=slots,
            flat_dim=flat_dim,
            coord_table=np.zeros((flat_dim, 3), dtype=np.float32),
            field_ids=np.concatenate(
                [
                    np.full(slot.end - slot.start, slot.field_id, dtype=np.int64)
                    for slot in slots
                ]
            ),
        )
        bundle_path = self.artifact_dir / Path(str(payload["model_path"])).name
        self.model, self.train_cfg = load_model_bundle(
            bundle_path,
            schema=self.hierarchical_schema,
            device=self.device,
        )
        if dict(payload["train_cfg"]) != asdict(self.train_cfg):
            raise ValueError(
                "checkpoint model training config does not match its manifest"
            )
        quality_policy = quality_policy_from_mapping(payload.get("quality_policy"))
        expected_signature = semantic_state_signature(
            strategy_signature=str(payload["strategy_signature"]),
            parameter_names=self.parameter_names,
            parameter_definition_signature=current_parameter_signature,
            schema=self.hierarchical_schema,
            train_cfg=self.train_cfg,
            quality_policy=quality_policy,
            torch_version=str(payload["torch_version"]),
        )
        if str(payload["state_signature"]) != expected_signature:
            raise ValueError(
                "checkpoint semantic state does not match the current workspace"
            )

    def _matrix(self, normalized_rows: Sequence[Sequence[float]]) -> np.ndarray:
        matrix = np.asarray(normalized_rows, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix[None, :]
        if matrix.ndim != 2 or matrix.shape[1] != len(self.parameter_names):
            raise ValueError(
                f"expected normalized values with width {len(self.parameter_names)}"
            )
        return np.ascontiguousarray(np.clip(matrix, 0.0, 1.0))

    def _predict_member_flats(
        self,
        normalized_rows: Sequence[Sequence[float]],
        *,
        sample_batch: int | None = None,
    ) -> np.ndarray:
        matrix = self._matrix(normalized_rows)
        fields, _applicability, _residual = predict_hierarchical_members(
            model=self.model,
            parameters=matrix,
            device=self.device,
            batch_size=(
                self.train_cfg.inference_batch_size
                if sample_batch is None
                else max(1, int(sample_batch))
            ),
        )
        member_count = int(fields[0].shape[0])
        flats = np.empty(
            (member_count, len(matrix), self.schema.flat_dim), dtype=np.float64
        )
        for field_index, (slot, scaler, values) in enumerate(
            zip(
                self.schema.modeled_slots,
                self.hierarchical_schema.scalers,
                fields,
            )
        ):
            del field_index
            physical = (
                np.asarray(values, dtype=np.float64).reshape(
                    member_count, len(matrix), -1
                )
                * scaler.scale[None, None, :]
                + scaler.mean[None, None, :]
            )
            flats[:, :, slot.start : slot.end] = physical
        return np.ascontiguousarray(flats)

    def _samples_from_member_flats(
        self, member_flats: np.ndarray
    ) -> tuple[tuple[tuple[Mapping[str, object], ...], ...], ...]:
        output = []
        for member in member_flats:
            named = []
            for row_index in range(member.shape[0]):
                arrays = {}
                for slot, layout in zip(
                    self.schema.modeled_slots,
                    self.hierarchical_schema.layouts,
                ):
                    values = member[
                        row_index, slot.start : slot.end
                    ].reshape(layout.shape)
                    arrays[layout.selector] = values.astype(
                        np.dtype(layout.dtype), copy=False
                    )
                named.append(
                    self.hierarchical_schema.template.reconstruct(arrays)
                )
            output.append(
                tuple(
                    tuple(dict(item.payload) for item in sample.items)
                    for sample in named
                )
            )
        return tuple(output)

    def predict(
        self,
        normalized_rows: Sequence[Sequence[float]],
        *,
        include_members: bool = False,
    ):
        rows = tuple(tuple(float(value) for value in row) for row in normalized_rows)
        if not rows:
            return (), (), ()
        member_flats = self._predict_member_flats(rows)
        member_samples = self._samples_from_member_flats(member_flats)
        mean_flats = np.mean(member_flats, axis=0, dtype=np.float64)
        mean_samples = self._samples_from_member_flats(mean_flats[None, ...])[0]
        raw_rows = tuple(
            job_template_api.denormalize_variables(self.workspace, row)
            for row in rows
        )
        costs = job_template_api.calculate_cost(
            self.workspace, mean_samples, raw_variables=raw_rows
        )
        return (
            mean_samples,
            costs,
            member_samples if include_members else (),
        )

    def predict_plot(
        self,
        normalized_rows: Sequence[Sequence[float]],
        request: PlotRequest,
    ) -> tuple[PlotData, tuple[PlotData, ...]]:
        if not self.train_cfg.coordinate_readout:
            raise RuntimeError(
                "this hierarchical CAE checkpoint has no coordinate readout"
            )
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
            dimension.index not in selected and dimension.index not in fixed
            for dimension in dimensions
        ):
            raise ValueError("every unplotted dimension needs a fixed value")
        axes = tuple(
            (
                np.asarray(dimension.coordinates, dtype=np.float64)
                if dimension.index in selected
                else np.asarray([fixed[dimension.index]], dtype=np.float64)
            )
            for dimension in dimensions
        )
        layout = self.hierarchical_schema.layouts[item_index]
        points, output_shape, _axes = coordinate_grid(layout, axes)
        standardized = predict_hierarchical_coordinate_members(
            model=self.model,
            parameters=self._matrix(normalized_rows),
            field_index=item_index,
            coordinate_points=points,
            device=self.device,
            batch_size=self.train_cfg.inference_batch_size,
            query_batch_size=self.train_cfg.coordinate_query_batch_size,
        )
        if standardized.shape[1] != 1:
            raise ValueError("viewer plot prediction expects one parameter row")
        scaler = self.hierarchical_schema.scalers[item_index]
        means = interpolate_stored_values(layout, scaler.mean, points)
        scales = interpolate_stored_values(layout, scaler.scale, points)
        grids = (
            standardized[:, 0, :].astype(np.float64) * scales[None, :]
            + means[None, :]
        ).reshape((standardized.shape[0], *output_shape))
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
        rows = tuple(tuple(float(value) for value in row) for row in normalized_rows)
        true_flats = np.ascontiguousarray(true_flats, dtype=np.float64)
        if true_flats.shape != (len(rows), self.schema.flat_dim):
            raise ValueError(
                "true rawData matrix does not match checkpoint prediction dimensions"
            )
        raw_shape = (len(rows), len(self.schema.templates))
        output_costs = []
        raw_relative_sums = np.zeros(raw_shape, dtype=np.float64)
        raw_relative_counts = np.zeros(raw_shape, dtype=np.int64)
        raw_absolute_sums = np.zeros(raw_shape, dtype=np.float64)
        raw_absolute_counts = np.zeros(raw_shape, dtype=np.int64)
        size = max(1, int(batch_size))
        total = len(rows) if progress_total is None else int(progress_total)
        accelerated = (
            max(self.train_cfg.inference_batch_size, int(cuda_sample_batch))
            if self.device.type == "cuda"
            else self.train_cfg.inference_batch_size
        )
        for start in range(0, len(rows), size):
            _check_cancelled(cancel_event)
            batch = rows[start : start + size]
            members = self._predict_member_flats(batch, sample_batch=accelerated)
            mean_flats = np.mean(members, axis=0, dtype=np.float64)
            absolute = np.abs(mean_flats - true_flats[start : start + len(batch)])
            relative = absolute / np.maximum(
                np.abs(true_flats[start : start + len(batch)]),
                float(relative_epsilon),
            )
            row_slice = slice(start, start + len(batch))
            raw_absolute_sums[row_slice], raw_absolute_counts[row_slice] = (
                summarize_errors_by_item(self.schema, absolute)
            )
            raw_relative_sums[row_slice], raw_relative_counts[row_slice] = (
                summarize_errors_by_item(self.schema, relative)
            )
            mean_samples = self._samples_from_member_flats(mean_flats[None, ...])[0]
            raw_rows = tuple(
                job_template_api.denormalize_variables(self.workspace, row)
                for row in batch
            )
            output_costs.extend(
                tuple(float(value) for value in row)
                for row in job_template_api.calculate_cost(
                    self.workspace, mean_samples, raw_variables=raw_rows
                )
            )
            if progress is not None:
                completed = min(start + len(batch), len(rows))
                progress(
                    progress_offset + completed,
                    total,
                    f"Checkpoint {self.checkpoint.generation}: {completed}/{len(rows)}",
                )
        _check_cancelled(cancel_event)
        return _CheckpointAuditPrediction(
            costs=tuple(output_costs),
            raw_relative_sums=raw_relative_sums,
            raw_relative_counts=raw_relative_counts,
            raw_absolute_sums=raw_absolute_sums,
            raw_absolute_counts=raw_absolute_counts,
        )


__all__ = [
    "HierarchicalCAECheckpointPredictor",
    "discover_hierarchical_cae_checkpoints",
]
