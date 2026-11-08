"""Read-only viewer adapter for explicit PCA/SVD checkpoints."""

from __future__ import annotations

from importlib import metadata
import hashlib
import json
from pathlib import Path
import threading
from typing import Mapping, Sequence

import numpy as np

from yadof.config import load_config
from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_contract import NamedRawDataItem
from yadof.job_template.rawdata_template import RawDataSchemaTemplate
from yadof.surrogate.conditional_inr.types import RawArraySlot, RawDataSchema
from yadof.surrogate.linear_subspace import checkpoints
from yadof.surrogate.linear_subspace.model import predict_raw_data

from .rawdata import (
    copy_template,
    extract_plot,
    flatten_samples_for_schema,
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


def discover_pca_svd_checkpoints(
    checkpoint_dir: Path,
    *,
    parameter_definition_signature: Mapping[str, object] | None = None,
    strategy_signature: str | None = None,
) -> tuple[CheckpointInfo, ...]:
    """Return valid explicit PCA/SVD descriptors in generation order."""

    root = Path(checkpoint_dir).resolve()
    compatible_parameter_signature = (
        None
        if parameter_definition_signature is None
        else _json_normalized_mapping(parameter_definition_signature)
    )
    run_pattern = (
        "*"
        if strategy_signature is None
        else checkpoints.run_namespace_for_signature(strategy_signature)
    )
    paths = root.glob(
        f"runs/{run_pattern}/components/{checkpoints.COMPONENT_NAMESPACE}/"
        "generation_*.json"
    )
    selected: dict[tuple[str, int], CheckpointInfo] = {}
    for path in sorted(paths):
        try:
            payload = checkpoints.validate_manifest(
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
            sample_count = int(payload["sample_count"])
            fields = payload["fields"]
            if sample_count <= 0 or not isinstance(fields, list) or not fields:
                continue
            namespace_relative = Path(str(payload["namespace_manifest"]))
            if namespace_relative.is_absolute() or ".." in namespace_relative.parts:
                continue
            if (root / namespace_relative).resolve() != path.resolve():
                continue
            artifact_dir = checkpoints.resolve_artifact_dir(root, payload)
            artifact_path = artifact_dir / Path(str(payload["artifact_file"])).name
            if not artifact_path.is_file():
                continue
            if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != str(
                payload["artifact_sha256"]
            ):
                continue
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        candidate = CheckpointInfo(
            generation=generation,
            path=path.resolve(),
            sample_count=sample_count,
            member_count=1,
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


class PCASVDCheckpointPredictor:
    """One deterministic PCA/SVD checkpoint loaded without mutation."""

    def __init__(
        self,
        workspace: Path,
        checkpoint: CheckpointInfo,
        template_sample: Sequence[Mapping[str, object]],
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.checkpoint = checkpoint
        self._config = load_config(self.workspace)
        payload = checkpoints.validate_manifest(dict(checkpoint.payload))

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
        if str(payload["numpy_version"]) != np.__version__ or str(
            payload["torch_version"]
        ) != metadata.version("torch"):
            raise ValueError("checkpoint runtime versions do not match this viewer")
        self.parameter_names = current_names

        fields = payload.get("fields")
        templates = copy_template(template_sample)
        if not isinstance(fields, list) or len(fields) != len(templates):
            raise ValueError("checkpoint rawData fields do not match the template sample")
        named_items: list[NamedRawDataItem] = []
        slots: list[RawArraySlot] = []
        offset = 0
        for index, (raw_field, template) in enumerate(zip(fields, templates)):
            if not isinstance(raw_field, Mapping):
                raise ValueError("checkpoint rawData field must be an object")
            selector = tuple(str(value) for value in raw_field["selector"])
            if len(selector) != 2 or selector[1] not in template:
                raise ValueError("checkpoint rawData selector is absent from template")
            shape = tuple(int(value) for value in raw_field["shape"])
            values = np.asarray(template[selector[1]])
            if tuple(values.shape) != shape or str(values.dtype) != str(raw_field["dtype"]):
                raise ValueError("checkpoint rawData dtype/shape does not match template")
            named_items.append(NamedRawDataItem(selector[0], template))
            end = offset + int(values.size)
            slots.append(
                RawArraySlot(
                    item_index=index,
                    key=selector[1],
                    shape=shape,
                    dtype=str(raw_field["dtype"]),
                    start=offset,
                    end=end,
                    field_id=index,
                )
            )
            offset = end

        template = RawDataSchemaTemplate.from_items(tuple(named_items))
        if template.signature != str(payload["schema_signature"]):
            raise ValueError("checkpoint rawData schema does not match template")
        self.model = checkpoints.load_model(
            self._config.workspace.surrogate_checkpoint_dir,
            payload,
            template=template,
        )
        expected_signature = checkpoints.state_signature(
            strategy_signature=str(payload["strategy_signature"]),
            parameter_names=self.parameter_names,
            parameter_definition_signature=current_parameter_signature,
            schema_signature=template.signature,
            training_data_digest=str(payload["training_data_digest"]),
            settings=self.model.settings,
            numpy_version=np.__version__,
            torch_version=metadata.version("torch"),
        )
        if str(payload["state_signature"]) != expected_signature:
            raise ValueError("checkpoint semantic state is incompatible")
        self.schema = RawDataSchema(
            templates=templates,
            modeled_slots=tuple(slots),
            flat_dim=offset,
            coord_table=np.zeros((offset, 1), dtype=np.float32),
            field_ids=np.concatenate(
                tuple(
                    np.full(slot.end - slot.start, slot.field_id, dtype=np.int64)
                    for slot in slots
                )
            ),
        )

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
        rows = tuple(tuple(float(value) for value in row) for row in normalized_rows)
        if not rows:
            return (), (), ()
        structured = predict_raw_data(self.model, rows)
        samples = tuple(sample.cost_items() for sample in structured)
        raw_rows = tuple(
            job_template_api.denormalize_variables(self.workspace, row)
            for row in rows
        )
        costs = tuple(
            tuple(float(value) for value in row)
            for row in job_template_api.calculate_cost(
                self.workspace,
                samples,
                raw_variables=raw_rows,
            )
        )
        return samples, costs, ((samples,) if include_members else ())

    def predict_plot(
        self,
        normalized_rows: Sequence[Sequence[float]],
        request: PlotRequest,
    ) -> tuple[PlotData, tuple[PlotData, ...]]:
        samples, _costs, members = self.predict(
            normalized_rows,
            include_members=True,
        )
        if len(samples) != 1:
            raise ValueError("viewer plot prediction expects one parameter row")
        mean_plot = extract_plot(
            samples[0],
            request.item_index,
            request.plotted_dimensions,
            request.fixed_map,
        )
        member_plots = tuple(
            extract_plot(
                batch[0],
                request.item_index,
                request.plotted_dimensions,
                request.fixed_map,
            )
            for batch in members
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
    ):
        del cuda_sample_batch
        from .checkpoints import _CheckpointAuditPrediction

        rows = tuple(tuple(float(value) for value in row) for row in normalized_rows)
        truth = np.ascontiguousarray(true_flats, dtype=np.float64)
        if truth.shape != (len(rows), self.schema.flat_dim):
            raise ValueError(
                "true rawData matrix does not match checkpoint prediction dimensions"
            )
        shape = (len(rows), len(self.schema.templates))
        relative_sums = np.zeros(shape, dtype=np.float64)
        relative_counts = np.zeros(shape, dtype=np.int64)
        absolute_sums = np.zeros(shape, dtype=np.float64)
        absolute_counts = np.zeros(shape, dtype=np.int64)
        output_costs: list[tuple[float, ...]] = []
        size = max(1, int(batch_size))
        total = len(rows) if progress_total is None else int(progress_total)
        for start in range(0, len(rows), size):
            _check_cancelled(cancel_event)
            batch = rows[start : start + size]
            samples, costs, _members = self.predict(batch)
            predicted = flatten_samples_for_schema(self.schema, samples)
            actual = truth[start : start + len(batch)]
            absolute = np.abs(predicted - actual)
            relative = absolute / np.maximum(
                np.abs(actual),
                float(relative_epsilon),
            )
            row_slice = slice(start, start + len(batch))
            absolute_sums[row_slice], absolute_counts[row_slice] = (
                summarize_errors_by_item(self.schema, absolute)
            )
            relative_sums[row_slice], relative_counts[row_slice] = (
                summarize_errors_by_item(self.schema, relative)
            )
            output_costs.extend(costs)
            if progress is not None:
                completed = min(start + len(batch), len(rows))
                progress(
                    progress_offset + completed,
                    total,
                    f"Checkpoint {self.checkpoint.generation}: "
                    f"{completed}/{len(rows)} · deterministic PCA/SVD",
                )
        _check_cancelled(cancel_event)
        return _CheckpointAuditPrediction(
            costs=tuple(output_costs),
            raw_relative_sums=relative_sums,
            raw_relative_counts=relative_counts,
            raw_absolute_sums=absolute_sums,
            raw_absolute_counts=absolute_counts,
        )


__all__ = ["PCASVDCheckpointPredictor", "discover_pca_svd_checkpoints"]
