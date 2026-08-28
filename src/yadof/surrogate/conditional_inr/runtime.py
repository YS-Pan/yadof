from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import threading
from typing import Iterable, Mapping, Sequence

import numpy as np
import torch

from ...config import LoadedConfig, load_config
from ...job_template import api as job_template_api
from ...recorded_data import api as recorded_api
from ...recorded_data.session import CampaignSession
from ...task_snapshot import GenerationTaskSnapshot
from ...workspace import WorkspaceContext
from ...optimize.state import active_strategy_signature

from .checkpoints import (
    COMPONENT_NAMESPACE,
    new_publication_paths,
    resolve_artifact_dir,
    resolve_namespace_manifest_path,
    run_namespace_for_signature,
    schema_payload,
    semantic_state_signature,
    validate_manifest_identity,
    write_checkpoint,
)
from .metadata import monotonic_time, now_text, record_training_success
from .types import (
    Population,
    RawArraySlot,
    RawDataItem,
    RawDataSchema,
    RawSample,
    SurrogateState,
    TargetScaler,
    TrainingData,
)

from .modeling import (
    INRTrainConfig,
    MODEL_NAME,
    fit_deep_ensemble_conditional_inr,
    load_inr_artifacts,
    member_list,
    predict_conditional_inr_members,
)
from .settings import ConditionalINRSettings, DEFAULT_CONDITIONAL_INR_SETTINGS


StateKey = tuple[str, str, str, str, str, str]

_STATE_LOCK = threading.RLock()
_STATES: dict[StateKey, SurrogateState] = {}

_STANDALONE_STRATEGY_SIGNATURE = hashlib.sha256(
    b"yadof:standalone-surrogate-state:v1"
).hexdigest()


def strategy_signature_for_workspace(workspace: WorkspaceContext) -> str:
    """Return the active strategy, or a stable namespace for direct API use."""

    return active_strategy_signature(workspace) or _STANDALONE_STRATEGY_SIGNATURE


def workspace_state_key(config: LoadedConfig) -> StateKey:
    workspace = config.workspace
    return (
        str(workspace.root),
        str(workspace.config_file),
        str(workspace.recorded_data_dir),
        str(workspace.surrogate_checkpoint_dir),
        strategy_signature_for_workspace(workspace),
        COMPONENT_NAMESPACE,
    )

def _call_first(module, names: Iterable[str], *args, **kwargs):
    for name in names:
        func = getattr(module, name, None)
        if callable(func):
            return func(*args, **kwargs)
    raise AttributeError(f"{module.__name__} does not expose any of: {', '.join(names)}")


def _as_population(values) -> Population:
    if values is None:
        return ()
    rows = tuple(values)
    if not rows:
        return ()
    if rows and not isinstance(rows[0], (list, tuple, np.ndarray)):
        rows = (rows,)
    return tuple(tuple(float(value) for value in row) for row in rows)


def _load_rawdata_item(item: RawDataItem) -> dict[str, object]:
    if isinstance(item, (str, Path)):
        with np.load(item, allow_pickle=False) as data:
            return {key: data[key].copy() for key in data.files}
    return {str(key): value for key, value in dict(item).items()}


def _as_raw_samples(values) -> tuple[RawSample, ...]:
    if values is None:
        return ()
    samples: list[RawSample] = []
    for row in values:
        if isinstance(row, (str, Path, Mapping)):
            samples.append((_load_rawdata_item(row),))
        else:
            samples.append(tuple(_load_rawdata_item(item) for item in row))
    return tuple(samples)


def _load_training_data(workspace: WorkspaceContext) -> TrainingData:
    bundled = recorded_api.get_surrogate_training_data(workspace)
    names = bundled.get("parameter_names", ())
    variables = bundled.get("normalized_variables", ())
    raw_data = bundled.get("raw_data", ())
    return TrainingData(
        tuple(str(name) for name in names),
        _as_population(variables),
        _as_raw_samples(raw_data),
    )


def _costs_from_raw(
    workspace: WorkspaceContext,
    raw_samples: Sequence[Sequence[RawDataItem]],
    normalized_variables: Sequence[Sequence[float]] | None = None,
) -> tuple[tuple[float, ...], ...]:
    samples = tuple(tuple(sample) for sample in raw_samples)
    raw_variables = (
        tuple(
            job_template_api.denormalize_variables(workspace, row)
            for row in normalized_variables
        )
        if normalized_variables is not None
        else None
    )
    raw_costs = job_template_api.calculate_costs_from_raw_data(
        workspace,
        samples,
        raw_variables=raw_variables,
    )
    return tuple(tuple(float(value) for value in row) for row in raw_costs)


def training_data_from_session(
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
) -> TrainingData:
    historical = session.historical_results(snapshot)
    names = tuple(name for name, _variables, _costs in historical)
    samples = dict(
        session.rawdata_samples(job_names=names, status="completed")
    )
    variables = []
    raw_data = []
    for name, normalized, _costs in historical:
        sample = samples.get(name)
        if sample is None:
            continue
        variables.append(tuple(normalized))
        raw_data.append(tuple(sample))
    return TrainingData(
        parameter_names=tuple(snapshot.parameter_names),
        normalized_variables=tuple(variables),
        raw_data=_as_raw_samples(tuple(raw_data)),
    )


def _copy_template_value(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, Mapping):
        return {str(key): _copy_template_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_copy_template_value(item) for item in value)
    return value


def _is_numeric_array(value: object) -> bool:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError):
        return False
    return np.issubdtype(array.dtype, np.number) and array.dtype != np.dtype("O")


def _finite_fill_vector(values: np.ndarray) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float64).reshape(-1)
    if vector.size == 0 or np.isfinite(vector).all():
        return np.ascontiguousarray(vector, dtype=np.float64)

    finite = np.isfinite(vector)
    if not np.any(finite):
        return np.zeros_like(vector, dtype=np.float64)

    indices = np.arange(vector.size, dtype=np.float64)
    filled = np.interp(indices, indices[finite], vector[finite])
    return np.ascontiguousarray(filled, dtype=np.float64)


def _finite_fill_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("surrogate target matrix must be two-dimensional")
    if matrix.size == 0 or np.isfinite(matrix).all():
        return np.ascontiguousarray(matrix, dtype=np.float64)
    return np.stack([_finite_fill_vector(row) for row in matrix], axis=0)


def _numeric_array_nonfinite_fraction(value: object) -> float | None:
    if not _is_numeric_array(value):
        return None
    array = np.asarray(value, dtype=np.float64)
    if array.size == 0:
        return 0.0
    return float(np.count_nonzero(~np.isfinite(array)) / array.size)


def _sample_exceeds_nonfinite_fraction(raw_sample: RawSample, threshold: float) -> bool:
    threshold = max(0.0, min(1.0, float(threshold)))
    for item in raw_sample:
        loaded = _load_rawdata_item(item)
        for key, value in loaded.items():
            if str(key) == "metadata":
                continue
            fraction = _numeric_array_nonfinite_fraction(value)
            if fraction is not None and fraction > threshold:
                return True
    return False


def _filter_training_data_by_nonfinite_fraction(
    data: TrainingData, *, threshold: float = 0.20
) -> tuple[TrainingData, int]:
    threshold = float(threshold)
    kept_variables: list[tuple[float, ...]] = []
    kept_raw_data: list[RawSample] = []
    dropped = 0
    for variables, raw_sample in zip(data.normalized_variables, data.raw_data):
        if _sample_exceeds_nonfinite_fraction(raw_sample, threshold):
            dropped += 1
            continue
        kept_variables.append(tuple(float(value) for value in variables))
        kept_raw_data.append(raw_sample)
    return (
        TrainingData(
            parameter_names=data.parameter_names,
            normalized_variables=tuple(kept_variables),
            raw_data=tuple(kept_raw_data),
        ),
        int(dropped),
    )


def _normalize_samples(raw_samples: tuple[RawSample, ...]) -> tuple[tuple[dict[str, object], ...], ...]:
    return tuple(tuple(_load_rawdata_item(item) for item in sample) for sample in raw_samples)


def _metadata_dict(value: object) -> dict[str, object]:
    raw = value
    if isinstance(raw, np.ndarray):
        raw = raw.item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _metadata_array(metadata: Mapping[str, object]) -> np.ndarray:
    return np.asarray(json.dumps(dict(metadata), ensure_ascii=False), dtype=np.str_)


def _normalized_axis(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if values.size == 0:
        return values.astype(np.float64)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros_like(values, dtype=np.float64)
    lo = float(np.min(finite))
    hi = float(np.max(finite))
    if hi <= lo:
        return np.zeros_like(values, dtype=np.float64)
    return np.ascontiguousarray(2.0 * (values - lo) / (hi - lo) - 1.0, dtype=np.float64)


def _physical_axis_values_for_dim(
    template: Mapping[str, object],
    shape: tuple[int, ...],
    dim: int,
) -> np.ndarray:
    size = int(shape[dim])
    metadata = _metadata_dict(template.get("metadata"))
    axes = metadata.get("axes")
    if isinstance(axes, Sequence) and not isinstance(axes, (str, bytes, Mapping)) and dim < len(axes):
        descriptor = axes[dim]
        if isinstance(descriptor, Mapping):
            values_key = descriptor.get("values_key")
            if isinstance(values_key, str) and values_key in template and _is_numeric_array(template[values_key]):
                values = np.asarray(template[values_key], dtype=np.float64).reshape(-1)
                if values.size == size:
                    return values
    return np.arange(size, dtype=np.float64)


def _axis_values_for_dim(template: Mapping[str, object], shape: tuple[int, ...], dim: int) -> np.ndarray:
    return _normalized_axis(
        _physical_axis_values_for_dim(template, shape, dim)
    )


def _slot_coordinates(template: Mapping[str, object], slot: RawArraySlot) -> np.ndarray:
    shape = tuple(int(value) for value in slot.shape)
    if not shape:
        return np.zeros((1, 3), dtype=np.float32)

    indices = np.indices(shape, sparse=False)
    coords = np.zeros((int(np.prod(shape, dtype=np.int64)), 3), dtype=np.float64)
    for dim in range(min(len(shape), 3)):
        axis_values = _axis_values_for_dim(template, shape, dim)
        coords[:, dim] = axis_values[indices[dim].reshape(-1)]
    return np.ascontiguousarray(coords, dtype=np.float32)


def _build_query_table(schema: RawDataSchema) -> tuple[np.ndarray, np.ndarray]:
    if not schema.modeled_slots:
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0,), dtype=np.int64)
    coords = []
    fields = []
    for slot in schema.modeled_slots:
        slot_coords = _slot_coordinates(schema.templates[slot.item_index], slot)
        coords.append(slot_coords)
        fields.append(np.full((slot_coords.shape[0],), int(slot.field_id), dtype=np.int64))
    return (
        np.ascontiguousarray(np.concatenate(coords, axis=0), dtype=np.float32),
        np.ascontiguousarray(np.concatenate(fields, axis=0), dtype=np.int64),
    )


def _interpolate_regular_grid(
    values: np.ndarray,
    source_axes: Sequence[np.ndarray],
    target_axes: Sequence[np.ndarray],
) -> np.ndarray:
    """Linearly interpolate one regular grid, clamping scaler extrapolation."""

    result = np.asarray(values, dtype=np.float64)
    for axis, (raw_source, raw_target) in enumerate(
        zip(source_axes, target_axes)
    ):
        source = np.asarray(raw_source, dtype=np.float64).reshape(-1)
        target = np.asarray(raw_target, dtype=np.float64).reshape(-1)
        if source.size != result.shape[axis]:
            raise ValueError("source axis does not match scaler grid")
        if not np.all(np.isfinite(source)) or not np.all(np.isfinite(target)):
            raise ValueError("off-grid rawData coordinates must be finite")
        if np.array_equal(source, target):
            continue

        moved = np.moveaxis(result, axis, 0)
        flat = moved.reshape(source.size, -1)
        if source.size <= 1:
            interpolated = np.repeat(flat[:1], target.size, axis=0)
        else:
            order = np.argsort(source, kind="stable")
            ordered_source = source[order]
            if np.any(np.diff(ordered_source) <= 0.0):
                raise ValueError(
                    "off-grid rawData queries require unique axis coordinates"
                )
            ordered_values = flat[order]
            interpolated = np.empty(
                (target.size, ordered_values.shape[1]),
                dtype=np.float64,
            )
            for column in range(ordered_values.shape[1]):
                interpolated[:, column] = np.interp(
                    target,
                    ordered_source,
                    ordered_values[:, column],
                )
        reshaped = interpolated.reshape((target.size, *moved.shape[1:]))
        result = np.moveaxis(reshaped, 0, axis)
    return np.ascontiguousarray(result, dtype=np.float64)


def predict_rawdata_slot_members_at_coordinates(
    *,
    model: object,
    schema: RawDataSchema,
    scaler: TargetScaler,
    train_cfg: INRTrainConfig,
    device: torch.device,
    normalized_rows: Sequence[Sequence[float]],
    item_index: int,
    key: str,
    axis_coordinates: Sequence[Sequence[float] | np.ndarray],
) -> np.ndarray:
    """Query one modeled rawData slot at arbitrary physical coordinates.

    Existing full-grid prediction does not call this function. At stored
    coordinates this uses the same decoder coordinates and target scaler as
    the legacy path; between coordinates it linearly interpolates the stored
    per-coordinate scaler before inverse scaling the decoder output.
    """

    slot = next(
        (
            candidate
            for candidate in schema.modeled_slots
            if candidate.item_index == int(item_index)
            and candidate.key == str(key)
        ),
        None,
    )
    if slot is None:
        raise ValueError(
            f"rawData item {int(item_index)} field {str(key)!r} is not modeled"
        )

    shape = tuple(int(value) for value in slot.shape)
    if len(axis_coordinates) != len(shape):
        raise ValueError(
            f"expected {len(shape)} rawData coordinate axes, "
            f"got {len(axis_coordinates)}"
        )
    targets = tuple(
        np.asarray(values, dtype=np.float64).reshape(-1)
        for values in axis_coordinates
    )
    if any(values.size == 0 for values in targets):
        raise ValueError("off-grid rawData coordinate axes cannot be empty")

    template = schema.templates[slot.item_index]
    sources = tuple(
        _physical_axis_values_for_dim(template, shape, dim)
        for dim in range(len(shape))
    )
    if any(not np.all(np.isfinite(values)) for values in (*sources, *targets)):
        raise ValueError("off-grid rawData coordinates must be finite")
    for dim in range(3, len(shape)):
        if not np.array_equal(sources[dim], targets[dim]):
            raise ValueError(
                "this checkpoint only encodes the first three rawData "
                "dimensions; higher dimensions must keep their stored grid"
            )

    target_shape = tuple(int(values.size) for values in targets)
    query_count = int(np.prod(target_shape, dtype=np.int64)) if target_shape else 1
    coords = np.zeros((query_count, 3), dtype=np.float64)
    if target_shape:
        indices = np.indices(target_shape, sparse=False)
        for dim in range(min(len(shape), 3)):
            low = float(np.min(sources[dim]))
            high = float(np.max(sources[dim]))
            normalized_axis = (
                np.zeros_like(targets[dim], dtype=np.float64)
                if high <= low
                else 2.0 * (targets[dim] - low) / (high - low) - 1.0
            )
            coords[:, dim] = normalized_axis[indices[dim].reshape(-1)]

    matrix = _x_matrix(normalized_rows)
    scaled = predict_conditional_inr_members(
        model=model,
        X=matrix,
        coord_table=np.ascontiguousarray(coords, dtype=np.float32),
        field_ids=np.full(
            (query_count,),
            int(slot.field_id),
            dtype=np.int64,
        ),
        device=device,
        sample_batch=max(
            1,
            min(
                int(train_cfg.sample_batch_eval),
                int(max(1, matrix.shape[0])),
            ),
        ),
        query_batch=max(1, int(train_cfg.query_batch_eval)),
    )

    mean_grid = np.asarray(
        scaler.mean[slot.start : slot.end],
        dtype=np.float64,
    ).reshape(shape)
    scale_grid = np.asarray(
        scaler.scale[slot.start : slot.end],
        dtype=np.float64,
    ).reshape(shape)
    target_mean = _interpolate_regular_grid(
        mean_grid,
        sources,
        targets,
    ).reshape(-1)
    target_scale = _interpolate_regular_grid(
        scale_grid,
        sources,
        targets,
    ).reshape(-1)
    physical = (
        np.asarray(scaled, dtype=np.float64)
        * target_scale[None, None, :]
        + target_mean[None, None, :]
    )
    return np.ascontiguousarray(
        physical.reshape(
            (
                int(physical.shape[0]),
                int(physical.shape[1]),
                *target_shape,
            )
        ),
        dtype=np.float64,
    )


def _flatten_raw_samples(
    raw_samples: tuple[RawSample, ...], *, constant_atol: float = 1e-12
) -> tuple[RawDataSchema | None, np.ndarray]:
    samples = _normalize_samples(raw_samples)
    if not samples:
        return None, np.zeros((0, 0), dtype=np.float64)

    item_count = len(samples[0])
    if item_count == 0:
        empty = RawDataSchema(
            templates=(),
            modeled_slots=(),
            flat_dim=0,
            coord_table=np.zeros((0, 3), dtype=np.float32),
            field_ids=np.zeros((0,), dtype=np.int64),
        )
        return empty, np.zeros((len(samples), 0), dtype=np.float64)
    for sample in samples:
        if len(sample) != item_count:
            raise ValueError("all surrogate rawData samples must contain the same number of rawData items")

    templates = tuple(
        {str(key): _copy_template_value(value) for key, value in item.items()}
        for item in samples[0]
    )
    modeled_slots: list[RawArraySlot] = []
    columns: list[np.ndarray] = []
    offset = 0
    atol = float(constant_atol)

    for item_index, template in enumerate(templates):
        keys = tuple(template.keys())
        for sample in samples:
            if tuple(sample[item_index].keys()) != keys:
                raise ValueError("all surrogate rawData items must share the same keys")

        for key in keys:
            if key == "metadata" or not _is_numeric_array(template[key]):
                continue
            arrays = [np.asarray(sample[item_index][key], dtype=np.float64) for sample in samples]
            shape = arrays[0].shape
            if any(array.shape != shape for array in arrays):
                raise ValueError(f"rawData array {key!r} changed shape between samples")

            matrix = _finite_fill_matrix(np.stack([array.reshape(-1) for array in arrays], axis=0))
            if matrix.shape[1] == 0:
                continue
            spread = float(np.max(np.abs(matrix - matrix[0:1]))) if matrix.size else 0.0
            if len(samples) < 2 or spread <= atol:
                continue

            start = offset
            offset += int(matrix.shape[1])
            modeled_slots.append(
                RawArraySlot(
                    item_index=int(item_index),
                    key=str(key),
                    shape=tuple(int(value) for value in shape),
                    dtype=str(np.asarray(template[key]).dtype),
                    start=int(start),
                    end=int(offset),
                    field_id=int(len(modeled_slots)),
                )
            )
            columns.append(matrix)

    y = np.concatenate(columns, axis=1).astype(np.float64) if columns else np.zeros((len(samples), 0), dtype=np.float64)
    schema = RawDataSchema(
        templates=templates,
        modeled_slots=tuple(modeled_slots),
        flat_dim=int(y.shape[1]),
        coord_table=np.zeros((0, 3), dtype=np.float32),
        field_ids=np.zeros((0,), dtype=np.int64),
    )
    coord_table, field_ids = _build_query_table(schema)
    schema = RawDataSchema(
        templates=templates,
        modeled_slots=tuple(modeled_slots),
        flat_dim=int(y.shape[1]),
        coord_table=coord_table,
        field_ids=field_ids,
    )
    return schema, np.ascontiguousarray(y, dtype=np.float64)


def _raw_samples_from_flat(schema: RawDataSchema | None, y_flat: np.ndarray) -> tuple[RawSample, ...]:
    if schema is None:
        return ()

    y_flat = np.ascontiguousarray(y_flat, dtype=np.float64)
    if y_flat.ndim == 1:
        y_flat = y_flat[None, :]
    if y_flat.ndim != 2 or y_flat.shape[1] != int(schema.flat_dim):
        raise ValueError(f"expected raw surrogate flat shape [N, {int(schema.flat_dim)}], got {tuple(y_flat.shape)}")

    samples: list[RawSample] = []
    for row in y_flat:
        items = tuple(
            {str(key): _copy_template_value(value) for key, value in template.items()}
            for template in schema.templates
        )
        mutable_items = [dict(item) for item in items]

        for slot in schema.modeled_slots:
            values = row[slot.start : slot.end].reshape(slot.shape)
            template_value = schema.templates[slot.item_index][slot.key]
            dtype = np.asarray(template_value).dtype
            if np.issubdtype(dtype, np.integer):
                values = np.rint(values)
            mutable_items[slot.item_index][slot.key] = values.astype(dtype, copy=False)

        for item in mutable_items:
            if "metadata" not in item:
                continue
            metadata = _metadata_dict(item["metadata"])
            if metadata:
                metadata["source"] = "yadof.surrogate.conditional_inr.runtime"
                metadata["surrogate_prediction"] = True
                metadata["surrogate_model"] = MODEL_NAME
                metadata.pop("variables", None)
                item["metadata"] = _metadata_array(metadata)

        samples.append(tuple(mutable_items))
    return tuple(samples)


def _x_matrix(population: Population | Sequence[Sequence[float]], input_dim: int | None = None) -> np.ndarray:
    rows = _as_population(population)
    if not rows:
        width = 0 if input_dim is None else int(input_dim)
        return np.zeros((0, width), dtype=np.float32)
    matrix = np.asarray(rows, dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError("population must be a two-dimensional sequence")
    if input_dim is not None and matrix.shape[1] != int(input_dim):
        raise ValueError(f"expected population width {int(input_dim)}, got {matrix.shape[1]}")
    return np.ascontiguousarray(np.clip(matrix, 0.0, 1.0), dtype=np.float32)


def _fit_scaler(y: np.ndarray, *, scale_floor: float = 1e-6) -> TargetScaler:
    y = np.ascontiguousarray(y, dtype=np.float64)
    if y.ndim != 2:
        raise ValueError("target scaler expects Y[N,Q]")
    mean = np.mean(y, axis=0, dtype=np.float64)
    scale = np.std(y, axis=0, dtype=np.float64)
    floor = float(scale_floor)
    scale = np.maximum(scale, floor)
    return TargetScaler(
        mean=np.ascontiguousarray(mean, dtype=np.float64),
        scale=np.ascontiguousarray(scale, dtype=np.float64),
    )


def _train_config_from_settings(settings: ConditionalINRSettings) -> INRTrainConfig:
    return INRTrainConfig(
        epochs=settings.epochs,
        ensemble_size=settings.ensemble_size,
        batch_size=settings.batch_size,
        lr=settings.learning_rate,
        weight_decay=settings.weight_decay,
        loss_beta=settings.loss_beta,
        x_latent_dim=settings.x_latent_dim,
        field_emb_dim=settings.field_embedding_dim,
        coord_fourier_features=settings.coordinate_fourier_features,
        hidden_dim=settings.hidden_dim,
        hidden_layers=settings.hidden_layers,
        train_query_chunk=settings.train_query_chunk,
        train_query_sample_count=settings.train_query_sample_count,
        sample_batch_eval=settings.sample_batch_eval,
        query_batch_eval=settings.query_batch_eval,
        bootstrap_members=settings.bootstrap_members,
        bootstrap_fraction=settings.bootstrap_fraction,
    )


def _select_device(requested: str) -> torch.device:
    requested = str(requested).lower()
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return torch.device("xpu")
    return torch.device("cpu")


def _predict_model_flats(
    state: SurrogateState,
    x: np.ndarray,
    model: object,
) -> np.ndarray:
    if state.model is None or state.schema is None or state.scaler is None or state.schema.flat_dim == 0:
        flat_dim = 0 if state.schema is None else int(state.schema.flat_dim)
        return np.zeros((1, x.shape[0], flat_dim), dtype=np.float64)
    if state.train_cfg is None or state.device is None:
        raise ValueError("surrogate state is missing train config or device")
    scaled = predict_conditional_inr_members(
        model=model,
        X=np.ascontiguousarray(x, dtype=np.float32),
        coord_table=state.schema.coord_table,
        field_ids=state.schema.field_ids,
        device=state.device,
        sample_batch=max(1, min(int(state.train_cfg.sample_batch_eval), int(max(1, x.shape[0])))),
        query_batch=max(1, int(state.train_cfg.query_batch_eval)),
    )
    return state.scaler.inverse_members(scaled)


def _predict_member_flats(state: SurrogateState, x: np.ndarray) -> np.ndarray:
    return _predict_model_flats(state, x, state.model)


def _predict_selected_member_flat(
    state: SurrogateState,
    x: np.ndarray,
    member_index: int,
) -> np.ndarray:
    """Predict one complete ensemble member without changing legacy outputs."""

    if state.model is None:
        raise ValueError("surrogate state has no model")
    members = member_list(state.model)
    selected = int(member_index)
    if selected < 0 or selected >= len(members):
        raise IndexError(
            f"conditional-INR member index {selected} is outside [0, {len(members)})"
        )
    return _predict_model_flats(state, x, members[selected])[0]


def train(
    workspace: WorkspaceContext | str | Path,
    *,
    generation_index: int = 0,
    started_at: str | None = None,
    _settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
) -> SurrogateState:
    return train_with_config(
        load_config(workspace),
        generation_index=generation_index,
        started_at=started_at,
        settings=_settings,
    )


def train_with_config(
    config: LoadedConfig,
    *,
    generation_index: int = 0,
    started_at: str | None = None,
    training_data: TrainingData | None = None,
    settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
    random_seed: int | None = None,
) -> SurrogateState:

    training_started_at = now_text() if started_at is None else str(started_at)
    started_monotonic = monotonic_time()

    data = training_data or _load_training_data(config.workspace)
    if len(data.normalized_variables) != len(data.raw_data):
        raise ValueError("surrogate training needs one rawData sample per normalized variable row")
    raw_sample_count = len(data.raw_data)
    nonfinite_threshold = settings.max_nonfinite_fraction
    data, dropped_nonfinite_samples = _filter_training_data_by_nonfinite_fraction(
        data, threshold=nonfinite_threshold
    )

    x = _x_matrix(data.normalized_variables)
    schema, y = _flatten_raw_samples(
        data.raw_data, constant_atol=settings.constant_atol
    )
    trainable = bool(
        x.shape[0] >= 2
        and y.shape[1] > 0
        and schema is not None
        and schema.n_fields > 0
    )
    model = None
    scaler = None
    train_cfg = _train_config_from_settings(settings) if trainable else None
    device = None
    parameter_definition_signature = (
        job_template_api.get_parameter_definition_signature(config.workspace)
    )
    strategy_signature = strategy_signature_for_workspace(config.workspace)
    state_signature = semantic_state_signature(
        strategy_signature=strategy_signature,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema=schema,
        train_cfg=train_cfg,
    )
    (
        checkpoint_path,
        namespace_manifest_path,
        artifact_dir,
        staged_artifact_dir,
        run_namespace,
        component_namespace,
    ) = new_publication_paths(
        config.workspace.surrogate_checkpoint_dir,
        generation_index=int(generation_index),
        strategy_signature=strategy_signature,
    )
    model_path = artifact_dir / "model_aux.npz"
    history: dict[str, object] = {
        "model": MODEL_NAME,
        "training_policy": "real_field_balanced",
        "member_count": 0,
        "train_sample_count": int(x.shape[0]),
        "raw_sample_count_before_filter": int(raw_sample_count),
        "dropped_nonfinite_samples": int(dropped_nonfinite_samples),
        "nonfinite_drop_threshold": nonfinite_threshold,
        "query_count": int(y.shape[1]),
        "device": "",
        "skipped": True,
        "skip_reason": "no varying rawData slots or not enough samples",
    }

    if trainable:
        scaler = _fit_scaler(
            y, scale_floor=settings.target_scale_floor
        )
        device = _select_device(settings.device)
        y_scaled = scaler.transform(y)
        model, history = fit_deep_ensemble_conditional_inr(
            input_dim=int(x.shape[1]),
            n_fields=int(schema.n_fields),
            X_train=np.ascontiguousarray(x, dtype=np.float32),
            Y_train=y_scaled,
            coord_table=schema.coord_table,
            field_ids=schema.field_ids,
            device=device,
            train_cfg=train_cfg,
            artifact_dir=staged_artifact_dir,
            seed=int(
                config.OPTIMIZE_RANDOM_SEED if random_seed is None else random_seed
            ) + int(generation_index) * 1009,
        )
        history["skipped"] = False
        history["raw_sample_count_before_filter"] = int(raw_sample_count)
        history["dropped_nonfinite_samples"] = int(dropped_nonfinite_samples)
        history["nonfinite_drop_threshold"] = nonfinite_threshold
        history["target_scaler"] = "per_query_mean_standard_deviation"
    else:
        staged_artifact_dir.mkdir(parents=True, exist_ok=True)

    state = SurrogateState(
        generation_index=int(generation_index),
        sample_count=len(data.normalized_variables),
        checkpoint_path=checkpoint_path,
        namespace_manifest_path=namespace_manifest_path,
        model_path=model_path,
        artifact_dir=artifact_dir,
        model_name=MODEL_NAME,
        strategy_signature=strategy_signature,
        state_signature=state_signature,
        run_namespace=run_namespace,
        component_namespace=component_namespace,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema=schema,
        scaler=scaler,
        model=model,
        train_cfg=train_cfg,
        device=device,
        train_history=history,
    )
    write_checkpoint(state, staged_artifact_dir=staged_artifact_dir)
    ended_at = now_text()
    record_training_success(
        config.workspace,
        state,
        started_at=training_started_at,
        ended_at=ended_at,
        duration_sec=monotonic_time() - started_monotonic,
    )
    with _STATE_LOCK:
        key = workspace_state_key(config)
        if _is_usable_state(state):
            _STATES[key] = state
        else:
            _STATES.pop(key, None)
    return state


def _is_usable_state(state: SurrogateState | None) -> bool:
    return bool(
        state is not None
        and state.model is not None
        and state.schema is not None
        and state.schema.flat_dim > 0
        and state.schema.n_fields > 0
        and state.scaler is not None
        and state.train_cfg is not None
        and not bool(state.train_history.get("skipped", False))
    )


def has_trained_state(
    workspace: WorkspaceContext | str | Path,
    *,
    _settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
) -> bool:
    config = load_config(workspace)
    return _is_usable_state(
        _state_for_config(config, settings=_settings, recover=True)
    )


def latest_state_generation(
    workspace: WorkspaceContext | str | Path,
    *,
    _settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
) -> int | None:
    config = load_config(workspace)
    state = _state_for_config(config, settings=_settings, recover=True)
    return int(state.generation_index) if _is_usable_state(state) else None


def reset_workspace_state(workspace: WorkspaceContext | str | Path) -> None:
    """Forget only one workspace's in-memory surrogate state."""

    config = load_config(workspace)
    with _STATE_LOCK:
        _STATES.pop(workspace_state_key(config), None)


def _require_state(
    config: LoadedConfig,
    settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
) -> SurrogateState:
    state = _state_for_config(config, settings=settings, recover=True)
    if not _is_usable_state(state):
        raise RuntimeError("surrogate model is not trained")
    assert state is not None
    return state


def _state_for_config(
    config: LoadedConfig,
    *,
    settings: ConditionalINRSettings,
    recover: bool,
) -> SurrogateState | None:
    key = workspace_state_key(config)
    with _STATE_LOCK:
        state = _STATES.get(key)
    if state is not None and not _is_usable_state(state):
        with _STATE_LOCK:
            _STATES.pop(key, None)
        state = None
    if state is not None:
        current_parameter_definition_signature = (
            job_template_api.get_parameter_definition_signature(config.workspace)
        )
        current_train_cfg = (
            _train_config_from_settings(settings)
            if state.train_cfg is not None
            else None
        )
        expected_signature = semantic_state_signature(
            strategy_signature=strategy_signature_for_workspace(config.workspace),
            parameter_names=state.parameter_names,
            parameter_definition_signature=current_parameter_definition_signature,
            schema=state.schema,
            train_cfg=current_train_cfg,
        )
        if expected_signature != state.state_signature:
            with _STATE_LOCK:
                _STATES.pop(key, None)
            state = None
    if state is not None or not recover:
        return state
    state = _recover_latest_state(config, settings=settings)
    if state is None:
        return None
    with _STATE_LOCK:
        return _STATES.setdefault(key, state)


def _recover_latest_state(
    config: LoadedConfig,
    *,
    settings: ConditionalINRSettings,
) -> SurrogateState | None:
    checkpoint_dir = config.workspace.surrogate_checkpoint_dir
    if not checkpoint_dir.is_dir():
        return None

    data = _load_training_data(config.workspace)
    if len(data.normalized_variables) != len(data.raw_data):
        return None
    data, _dropped = _filter_training_data_by_nonfinite_fraction(
        data, threshold=settings.max_nonfinite_fraction
    )
    x = _x_matrix(data.normalized_variables)
    schema, current_flat = _flatten_raw_samples(
        data.raw_data, constant_atol=settings.constant_atol
    )
    trainable = bool(
        x.shape[0] >= 2
        and current_flat.shape[1] > 0
        and schema is not None
        and schema.n_fields > 0
    )
    if not trainable:
        return None
    train_cfg = _train_config_from_settings(settings) if trainable else None
    parameter_definition_signature = (
        job_template_api.get_parameter_definition_signature(config.workspace)
    )
    strategy_signature = strategy_signature_for_workspace(config.workspace)
    expected_signature = semantic_state_signature(
        strategy_signature=strategy_signature,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema=schema,
        train_cfg=train_cfg,
    )
    namespace_dir = (
        checkpoint_dir
        / "runs"
        / run_namespace_for_signature(strategy_signature)
        / "components"
        / COMPONENT_NAMESPACE
    )
    candidates = sorted(namespace_dir.glob("generation_*.json"), reverse=True)
    for checkpoint_path in candidates:
        try:
            return _recover_state_from_checkpoint(
                config,
                checkpoint_path,
                data=data,
                x=x,
                schema=schema,
                current_flat=current_flat,
                train_cfg=train_cfg,
                parameter_definition_signature=parameter_definition_signature,
                expected_signature=expected_signature,
                device_name=settings.device,
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return None


def _recover_state_from_checkpoint(
    config: LoadedConfig,
    checkpoint_path: Path,
    *,
    data: TrainingData,
    x: np.ndarray,
    schema: RawDataSchema | None,
    current_flat: np.ndarray,
    train_cfg: INRTrainConfig | None,
    parameter_definition_signature: Mapping[str, object],
    expected_signature: str,
    device_name: str,
) -> SurrogateState:
    payload = validate_manifest_identity(
        json.loads(checkpoint_path.read_text(encoding="utf-8"))
    )
    if str(payload["state_signature"]) != expected_signature:
        raise ValueError("surrogate checkpoint state signature is not current")
    strategy_signature = strategy_signature_for_workspace(config.workspace)
    if str(payload["strategy_signature"]) != strategy_signature:
        raise ValueError("surrogate checkpoint strategy signature is not active")
    if tuple(str(name) for name in payload["parameter_names"]) != data.parameter_names:
        raise ValueError("current workspace parameters do not match checkpoint")
    if dict(payload["schema"]) != schema_payload(schema):
        raise ValueError("surrogate checkpoint schema manifest is not current")
    if not isinstance(payload["train_cfg"], Mapping) or dict(
        payload["train_cfg"]
    ) != asdict(train_cfg):
        raise ValueError("surrogate checkpoint train config manifest is not current")
    manifest_signature = semantic_state_signature(
        strategy_signature=strategy_signature,
        parameter_names=data.parameter_names,
        parameter_definition_signature=dict(
            payload["parameter_definition_signature"]
        ),
        schema=schema,
        train_cfg=train_cfg,
        torch_version=str(payload["torch_version"]),
    )
    if manifest_signature != str(payload["state_signature"]):
        raise ValueError("surrogate checkpoint manifest signature is inconsistent")
    generation_index = int(payload["generation_index"])
    checkpoint_root = config.workspace.surrogate_checkpoint_dir
    namespace_manifest_path = resolve_namespace_manifest_path(checkpoint_root, payload)
    if namespace_manifest_path.resolve() != checkpoint_path.resolve():
        raise ValueError(
            "surrogate recovery candidate is not its declared namespace manifest"
        )
    artifact_dir = resolve_artifact_dir(checkpoint_root, payload)
    model_name = Path(str(payload["model_path"])).name
    model_path = artifact_dir / model_name
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    with np.load(model_path, allow_pickle=False) as auxiliary:
        required_arrays = {
            "schema_flat_dim",
            "training_sample_count",
            "target_mean",
            "target_scale",
            "coord_table",
            "field_ids",
        }
        missing_arrays = required_arrays.difference(auxiliary.files)
        if missing_arrays:
            raise ValueError(
                "surrogate checkpoint is missing required arrays: "
                + ", ".join(sorted(missing_arrays))
            )
        flat_dim = int(np.asarray(auxiliary["schema_flat_dim"]).item())
        artifact_sample_count = int(
            np.asarray(auxiliary["training_sample_count"]).item()
        )
        target_mean = np.asarray(auxiliary["target_mean"], dtype=np.float64)
        target_scale = np.asarray(auxiliary["target_scale"], dtype=np.float64)
        coord_table = np.asarray(auxiliary["coord_table"], dtype=np.float32)
        field_ids = np.asarray(auxiliary["field_ids"], dtype=np.int64)

    if schema is None or int(schema.flat_dim) != flat_dim:
        raise ValueError("current workspace rawData schema does not match checkpoint")
    if artifact_sample_count != int(payload["sample_count"]):
        raise ValueError("surrogate checkpoint sample counts do not agree")
    if target_mean.size != flat_dim or target_scale.size != flat_dim:
        raise ValueError("surrogate checkpoint target scaler does not match schema")
    if not np.array_equal(coord_table, schema.coord_table) or not np.array_equal(
        field_ids, schema.field_ids
    ):
        raise ValueError("current workspace rawData queries do not match checkpoint")

    if train_cfg is None or current_flat.shape[1] == 0:
        raise ValueError("checkpoint does not describe a trainable surrogate state")
    device = _select_device(device_name)
    scaler = TargetScaler(
        mean=np.ascontiguousarray(target_mean, dtype=np.float64),
        scale=np.ascontiguousarray(target_scale, dtype=np.float64),
    )
    meta_path = artifact_dir / "inr_meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(meta_path)
    model, input_dim, n_fields, loaded_train_cfg = load_inr_artifacts(
        artifact_dir, device
    )
    if loaded_train_cfg != train_cfg:
        raise ValueError("current surrogate train config does not match checkpoint")
    if int(input_dim) != int(x.shape[1]):
        raise ValueError("current workspace parameter width does not match checkpoint")
    if int(n_fields) != int(schema.n_fields):
        raise ValueError("current workspace rawData fields do not match checkpoint")

    active_manifest_path = checkpoint_root / f"generation_{generation_index:04d}.json"
    checkpoint_source = namespace_manifest_path
    try:
        active_payload = validate_manifest_identity(
            json.loads(active_manifest_path.read_text(encoding="utf-8"))
        )
        if active_payload == payload:
            checkpoint_source = active_manifest_path
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass

    state = SurrogateState(
        generation_index=generation_index,
        sample_count=int(payload["sample_count"]),
        checkpoint_path=checkpoint_source,
        namespace_manifest_path=namespace_manifest_path,
        model_path=model_path,
        artifact_dir=artifact_dir,
        model_name=str(payload["model"]),
        strategy_signature=strategy_signature,
        state_signature=expected_signature,
        run_namespace=str(payload["run_namespace"]),
        component_namespace=str(payload["component_namespace"]),
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema=schema,
        scaler=scaler,
        model=model,
        train_cfg=train_cfg,
        device=device,
        train_history=dict(payload.get("train_history", {})),
    )
    return state


def _state_input_dim(state: SurrogateState) -> int:
    return len(state.parameter_names)


def predict_raw_data(
    workspace: WorkspaceContext | str | Path,
    population,
    *,
    _settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
) -> tuple[RawSample, ...]:
    config = load_config(workspace)
    state = _require_state(config, _settings)
    if state.schema is None or state.schema.flat_dim == 0:
        return tuple()
    x = _x_matrix(population, _state_input_dim(state))
    member_flats = _predict_member_flats(state, x)
    mean_flat = np.mean(member_flats, axis=0)
    return _raw_samples_from_flat(state.schema, mean_flat)


def predict_population(
    workspace: WorkspaceContext | str | Path,
    population,
    *,
    _settings: ConditionalINRSettings = DEFAULT_CONDITIONAL_INR_SETTINGS,
) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
    config = load_config(workspace)
    state = _require_state(config, _settings)
    normalized_population = _as_population(population)
    if not normalized_population:
        return ()
    if state.schema is None or state.schema.flat_dim == 0 or state.model is None:
        costs = tuple((float("inf"),) for _ in normalized_population)
        return tuple((row, tuple((value, value) for value in row)) for row in costs)

    x = _x_matrix(normalized_population, _state_input_dim(state))
    member_flats = _predict_member_flats(state, x)
    mean_flat = np.mean(member_flats, axis=0)
    predicted_raw = _raw_samples_from_flat(state.schema, mean_flat)
    costs = _costs_from_raw(
        config.workspace, predicted_raw, normalized_population
    )

    member_costs = []
    for member_idx in range(member_flats.shape[0]):
        try:
            member_raw = _raw_samples_from_flat(state.schema, member_flats[member_idx])
            member_costs.append(
                np.asarray(
                    _costs_from_raw(
                        config.workspace, member_raw, normalized_population
                    ),
                    dtype=np.float64,
                )
            )
        except Exception:
            continue
    if member_costs:
        member_cost_matrix = np.stack(member_costs, axis=0)
        interval_lower = np.min(member_cost_matrix, axis=0)
        interval_upper = np.max(member_cost_matrix, axis=0)
    else:
        fallback = np.asarray(costs, dtype=np.float64)
        interval_lower = fallback
        interval_upper = fallback

    out = []
    for row_idx, cost_row in enumerate(costs):
        intervals = []
        for cost_idx, value in enumerate(cost_row):
            lo = float(interval_lower[row_idx, cost_idx])
            hi = float(interval_upper[row_idx, cost_idx])
            intervals.append((min(lo, hi), max(lo, hi)))
        out.append((tuple(float(value) for value in cost_row), tuple(intervals)))
    return tuple(out)
