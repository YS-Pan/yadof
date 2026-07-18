from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import threading
from typing import Iterable, Mapping, Sequence

import numpy as np
import torch

from ..config import LoadedConfig, load_config
from ..job_template import api as job_template_api
from ..recorded_data import api as recorded_api
from ..workspace import WorkspaceContext

from .checkpoints import write_checkpoint
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
    fit_deep_ensemble_conditional_inr,
    load_inr_artifacts,
    predict_conditional_inr_members,
)


MODEL_NAME = "conditional_inr_rawdata_deep_ensemble"


StateKey = tuple[str, str, str, str]

_STATE_LOCK = threading.RLock()
_STATES: dict[StateKey, SurrogateState] = {}


def workspace_state_key(config: LoadedConfig) -> StateKey:
    workspace = config.workspace
    return (
        str(workspace.root),
        str(workspace.job_template_dir),
        str(workspace.recorded_data_dir),
        str(workspace.surrogate_checkpoint_dir),
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


def _axis_values_for_dim(template: Mapping[str, object], shape: tuple[int, ...], dim: int) -> np.ndarray:
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
                    return _normalized_axis(values)
    if size <= 1:
        return np.zeros((size,), dtype=np.float64)
    return np.linspace(-1.0, 1.0, size, dtype=np.float64)


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
                metadata["source"] = "yadof.surrogate.runtime"
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
    mean = np.min(y, axis=0)
    scale = np.max(y, axis=0) - mean
    floor = float(scale_floor)
    scale = np.maximum(scale, floor)
    return TargetScaler(
        mean=np.ascontiguousarray(mean, dtype=np.float32),
        scale=np.ascontiguousarray(scale, dtype=np.float32),
    )


def _train_config_from_loaded_config(config: LoadedConfig) -> INRTrainConfig:
    defaults = INRTrainConfig()
    return INRTrainConfig(
        epochs=int(getattr(config, "SURROGATE_INR_EPOCHS", defaults.epochs)),
        ensemble_size=int(getattr(config, "SURROGATE_INR_ENSEMBLE_SIZE", defaults.ensemble_size)),
        batch_size=int(getattr(config, "SURROGATE_INR_BATCH_SIZE", defaults.batch_size)),
        lr=float(getattr(config, "SURROGATE_INR_LR", defaults.lr)),
        weight_decay=float(getattr(config, "SURROGATE_INR_WEIGHT_DECAY", defaults.weight_decay)),
        loss_beta=float(getattr(config, "SURROGATE_INR_LOSS_BETA", defaults.loss_beta)),
        relative_loss_weight=float(
            getattr(config, "SURROGATE_INR_RELATIVE_LOSS_WEIGHT", defaults.relative_loss_weight)
        ),
        relative_loss_eps=float(getattr(config, "SURROGATE_INR_RELATIVE_LOSS_EPS", defaults.relative_loss_eps)),
        x_latent_dim=int(getattr(config, "SURROGATE_INR_X_LATENT_DIM", defaults.x_latent_dim)),
        field_emb_dim=int(getattr(config, "SURROGATE_INR_FIELD_EMB_DIM", defaults.field_emb_dim)),
        coord_fourier_features=int(
            getattr(config, "SURROGATE_INR_COORD_FOURIER_FEATURES", defaults.coord_fourier_features)
        ),
        hidden_dim=int(getattr(config, "SURROGATE_INR_HIDDEN_DIM", defaults.hidden_dim)),
        hidden_layers=int(getattr(config, "SURROGATE_INR_HIDDEN_LAYERS", defaults.hidden_layers)),
        train_query_chunk=int(getattr(config, "SURROGATE_INR_TRAIN_QUERY_CHUNK", defaults.train_query_chunk)),
        train_query_sample_count=int(
            getattr(config, "SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT", defaults.train_query_sample_count)
        ),
        sample_batch_eval=int(getattr(config, "SURROGATE_INR_SAMPLE_BATCH_EVAL", defaults.sample_batch_eval)),
        query_batch_eval=int(getattr(config, "SURROGATE_INR_QUERY_BATCH_EVAL", defaults.query_batch_eval)),
        bootstrap_members=bool(getattr(config, "SURROGATE_INR_BOOTSTRAP_MEMBERS", defaults.bootstrap_members)),
        bootstrap_fraction=float(getattr(config, "SURROGATE_INR_BOOTSTRAP_FRACTION", defaults.bootstrap_fraction)),
    )


def _select_device(config: LoadedConfig) -> torch.device:
    requested = str(getattr(config, "SURROGATE_TORCH_DEVICE", "auto")).lower()
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return torch.device("xpu")
    return torch.device("cpu")


def _predict_member_flats(state: SurrogateState, x: np.ndarray) -> np.ndarray:
    if state.model is None or state.schema is None or state.scaler is None or state.schema.flat_dim == 0:
        flat_dim = 0 if state.schema is None else int(state.schema.flat_dim)
        return np.zeros((1, x.shape[0], flat_dim), dtype=np.float64)
    if state.train_cfg is None or state.device is None:
        raise ValueError("surrogate state is missing train config or device")
    scaled = predict_conditional_inr_members(
        model=state.model,
        X=np.ascontiguousarray(x, dtype=np.float32),
        coord_table=state.schema.coord_table,
        field_ids=state.schema.field_ids,
        device=state.device,
        sample_batch=max(1, min(int(state.train_cfg.sample_batch_eval), int(max(1, x.shape[0])))),
        query_batch=max(1, int(state.train_cfg.query_batch_eval)),
    )
    return state.scaler.inverse_members(scaled)


def _relative_errors(
    true_costs, pred_costs, *, epsilon: float = 1e-8
) -> tuple[tuple[float, ...], ...]:
    rows = []
    for true_row, pred_row in zip(true_costs, pred_costs):
        row = []
        for true_value, pred_value in zip(true_row, pred_row):
            denom = max(abs(float(true_value)), float(epsilon))
            row.append(abs(float(pred_value) - float(true_value)) / denom)
        rows.append(tuple(row))
    return tuple(rows)


def _absolute_errors(true_costs, pred_costs) -> tuple[tuple[float, ...], ...]:
    rows = []
    for true_row, pred_row in zip(true_costs, pred_costs):
        row = []
        for true_value, pred_value in zip(true_row, pred_row):
            row.append(abs(float(pred_value) - float(true_value)))
        rows.append(tuple(row))
    return tuple(rows)


def _mean_relative_error(
    true_costs, pred_costs, *, epsilon: float = 1e-8
) -> float:
    values = [
        value
        for row in _relative_errors(true_costs, pred_costs, epsilon=epsilon)
        for value in row
        if math.isfinite(value)
    ]
    return float(sum(values) / len(values)) if values else 0.0


def _quantile_by_objective(rows, quantile: float) -> tuple[float, ...]:
    width = max((len(row) for row in rows), default=0)
    out = []
    for idx in range(width):
        values = [float(row[idx]) for row in rows if idx < len(row) and math.isfinite(float(row[idx]))]
        out.append(float(np.quantile(values, float(quantile))) if values else 0.0)
    return tuple(out)


def _flat_importance_weights(
    workspace: WorkspaceContext,
    config: LoadedConfig,
    schema: RawDataSchema | None,
    raw_sample: RawSample | None,
) -> np.ndarray:
    if schema is None or int(schema.flat_dim) == 0:
        return np.zeros((0,), dtype=np.float32)
    weights = np.ones((int(schema.flat_dim),), dtype=np.float32)
    if raw_sample is None:
        return weights

    try:
        func = getattr(job_template_api, "get_rawdata_importance_weights", None)
        if not callable(func):
            func = getattr(job_template_api, "calculate_rawdata_importance_weights", None)
        if not callable(func):
            return weights
        try:
            raw_weights = func(
                workspace,
                raw_sample,
                floor=float(getattr(config, "SURROGATE_RAWDATA_IMPORTANCE_FLOOR", 0.25)),
                boost=float(getattr(config, "SURROGATE_RAWDATA_IMPORTANCE_BOOST", 2.0)),
            )
        except TypeError:
            raw_weights = func(workspace, raw_sample)
    except Exception:
        return weights

    weight_items = tuple(dict(item) if isinstance(item, Mapping) else {} for item in raw_weights or ())
    for slot in schema.modeled_slots:
        if slot.item_index >= len(weight_items):
            continue
        raw_value = weight_items[slot.item_index].get(slot.key)
        if raw_value is None:
            continue
        array = np.asarray(raw_value, dtype=np.float32)
        if tuple(array.shape) != tuple(slot.shape):
            continue
        weights[slot.start : slot.end] = np.maximum(0.0, array.reshape(-1))
    return np.ascontiguousarray(weights, dtype=np.float32)


def _always_include_query_indices(schema: RawDataSchema | None) -> np.ndarray:
    """Return rawData query indices that should bypass stochastic subsampling."""

    if schema is None or int(schema.flat_dim) == 0:
        return np.zeros((0,), dtype=np.int64)
    chunks = [
        np.arange(int(slot.start), int(slot.end), dtype=np.int64)
        for slot in schema.modeled_slots
        if len(tuple(slot.shape)) <= 1
    ]
    if not chunks:
        return np.zeros((0,), dtype=np.int64)
    return np.ascontiguousarray(np.concatenate(chunks), dtype=np.int64)

def _predict_costs_for_error_audit(
    workspace: WorkspaceContext,
    state: SurrogateState,
    x: np.ndarray,
) -> tuple[tuple[float, ...], ...]:
    if state.schema is None or state.schema.flat_dim == 0 or state.model is None or x.shape[0] == 0:
        return ()
    member_flats = _predict_member_flats(state, x)
    mean_flat = np.mean(member_flats, axis=0)
    return _costs_from_raw(
        workspace, _raw_samples_from_flat(state.schema, mean_flat)
    )


def train(
    workspace: WorkspaceContext | str | Path,
    *,
    generation_index: int = 0,
    started_at: str | None = None,
) -> SurrogateState:
    return train_with_config(
        load_config(workspace),
        generation_index=generation_index,
        started_at=started_at,
    )


def train_with_config(
    config: LoadedConfig,
    *,
    generation_index: int = 0,
    started_at: str | None = None,
) -> SurrogateState:

    training_started_at = now_text() if started_at is None else str(started_at)
    started_monotonic = monotonic_time()

    data = _load_training_data(config.workspace)
    if len(data.normalized_variables) != len(data.raw_data):
        raise ValueError("surrogate training needs one rawData sample per normalized variable row")
    raw_sample_count = len(data.raw_data)
    nonfinite_threshold = float(config.SURROGATE_MAX_NONFINITE_FRACTION)
    data, dropped_nonfinite_samples = _filter_training_data_by_nonfinite_fraction(
        data, threshold=nonfinite_threshold
    )

    x = _x_matrix(data.normalized_variables)
    schema, y = _flatten_raw_samples(
        data.raw_data, constant_atol=float(config.SURROGATE_CONSTANT_ATOL)
    )
    true_costs = (
        _costs_from_raw(config.workspace, data.raw_data) if data.raw_data else ()
    )
    query_weights = _flat_importance_weights(
        config.workspace,
        config,
        schema,
        data.raw_data[0] if data.raw_data else None,
    )

    checkpoint_path = (
        config.workspace.surrogate_checkpoint_dir
        / f"generation_{int(generation_index):04d}.json"
    )
    artifact_dir = checkpoint_path.parent / f"generation_{int(generation_index):04d}_conditional_inr"
    model_path = artifact_dir / "model_aux.npz"

    model = None
    scaler = None
    train_cfg = None
    device = None
    history: dict[str, object] = {
        "model": MODEL_NAME,
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

    if x.shape[0] >= 2 and y.shape[1] > 0 and schema is not None and schema.n_fields > 0:
        scaler = _fit_scaler(
            y, scale_floor=float(config.SURROGATE_TARGET_SCALE_FLOOR)
        )
        train_cfg = _train_config_from_loaded_config(config)
        device = _select_device(config)
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
            query_weights=query_weights,
            always_include_query_indices=_always_include_query_indices(schema),
            artifact_dir=artifact_dir,
            seed=int(getattr(config, "OPTIMIZE_RANDOM_SEED", 20260510)) + int(generation_index) * 1009,
        )
        history["skipped"] = False
        history["artifact_dir"] = str(artifact_dir)
        history["raw_sample_count_before_filter"] = int(raw_sample_count)
        history["dropped_nonfinite_samples"] = int(dropped_nonfinite_samples)
        history["nonfinite_drop_threshold"] = nonfinite_threshold
    else:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    state = SurrogateState(
        generation_index=int(generation_index),
        sample_count=len(data.normalized_variables),
        checkpoint_path=checkpoint_path,
        model_path=model_path,
        artifact_dir=artifact_dir,
        model_name=MODEL_NAME,
        parameter_names=data.parameter_names,
        normalized_variables=data.normalized_variables,
        raw_data=data.raw_data,
        schema=schema,
        scaler=scaler,
        model=model,
        train_cfg=train_cfg,
        device=device,
        train_history=history,
        training_flat_values=np.ascontiguousarray(y, dtype=np.float64),
        query_weights=np.ascontiguousarray(query_weights, dtype=np.float32),
        mean_relative_error=0.0,
        historical_relative_error_p50=(),
        historical_relative_error_p90=(),
        historical_relative_error_p95=(),
        historical_absolute_error_p90=(),
        historical_true_costs=true_costs,
        historical_predicted_costs=(),
    )

    try:
        pred_costs = _predict_costs_for_error_audit(config.workspace, state, x)
    except Exception as exc:
        pred_costs = ()
        history = {**state.train_history, "error_audit_error": f"{exc.__class__.__name__}: {exc}"}
        state = SurrogateState(
            generation_index=state.generation_index,
            sample_count=state.sample_count,
            checkpoint_path=state.checkpoint_path,
            model_path=state.model_path,
            artifact_dir=state.artifact_dir,
            model_name=state.model_name,
            parameter_names=state.parameter_names,
            normalized_variables=state.normalized_variables,
            raw_data=state.raw_data,
            schema=state.schema,
            scaler=state.scaler,
            model=state.model,
            train_cfg=state.train_cfg,
            device=state.device,
            train_history=history,
            training_flat_values=state.training_flat_values,
            query_weights=state.query_weights,
            mean_relative_error=state.mean_relative_error,
            historical_relative_error_p50=state.historical_relative_error_p50,
            historical_relative_error_p90=state.historical_relative_error_p90,
            historical_relative_error_p95=state.historical_relative_error_p95,
            historical_absolute_error_p90=state.historical_absolute_error_p90,
            historical_true_costs=state.historical_true_costs,
            historical_predicted_costs=state.historical_predicted_costs,
        )
    relative_error_epsilon = float(config.SURROGATE_RELATIVE_ERROR_EPS)
    mean_error = _mean_relative_error(
        true_costs, pred_costs, epsilon=relative_error_epsilon
    )
    rel_errors = _relative_errors(
        true_costs, pred_costs, epsilon=relative_error_epsilon
    )
    abs_errors = _absolute_errors(true_costs, pred_costs)
    state = SurrogateState(
        generation_index=state.generation_index,
        sample_count=state.sample_count,
        checkpoint_path=state.checkpoint_path,
        model_path=state.model_path,
        artifact_dir=state.artifact_dir,
        model_name=state.model_name,
        parameter_names=state.parameter_names,
        normalized_variables=state.normalized_variables,
        raw_data=state.raw_data,
        schema=state.schema,
        scaler=state.scaler,
        model=state.model,
        train_cfg=state.train_cfg,
        device=state.device,
        train_history=state.train_history,
        training_flat_values=state.training_flat_values,
        query_weights=state.query_weights,
        mean_relative_error=float(mean_error),
        historical_relative_error_p50=_quantile_by_objective(rel_errors, 0.50),
        historical_relative_error_p90=_quantile_by_objective(rel_errors, 0.90),
        historical_relative_error_p95=_quantile_by_objective(rel_errors, 0.95),
        historical_absolute_error_p90=_quantile_by_objective(abs_errors, 0.90),
        historical_true_costs=true_costs,
        historical_predicted_costs=pred_costs,
    )
    write_checkpoint(state)
    ended_at = now_text()
    record_training_success(
        config.workspace,
        state,
        started_at=training_started_at,
        ended_at=ended_at,
        duration_sec=monotonic_time() - started_monotonic,
    )
    with _STATE_LOCK:
        _STATES[workspace_state_key(config)] = state
    return state


def has_trained_state(workspace: WorkspaceContext | str | Path) -> bool:
    config = load_config(workspace)
    return _state_for_config(config, recover=True) is not None


def latest_state_generation(
    workspace: WorkspaceContext | str | Path,
) -> int | None:
    config = load_config(workspace)
    state = _state_for_config(config, recover=True)
    return None if state is None else int(state.generation_index)


def reset_workspace_state(workspace: WorkspaceContext | str | Path) -> None:
    """Forget only one workspace's in-memory surrogate state."""

    config = load_config(workspace)
    with _STATE_LOCK:
        _STATES.pop(workspace_state_key(config), None)


def _require_state(config: LoadedConfig) -> SurrogateState:
    state = _state_for_config(config, recover=True)
    if state is None:
        raise RuntimeError("surrogate model is not trained")
    return state


def _state_for_config(
    config: LoadedConfig, *, recover: bool
) -> SurrogateState | None:
    key = workspace_state_key(config)
    with _STATE_LOCK:
        state = _STATES.get(key)
    if state is not None or not recover:
        return state
    state = _recover_latest_state(config)
    if state is None:
        return None
    with _STATE_LOCK:
        return _STATES.setdefault(key, state)


def _recover_latest_state(config: LoadedConfig) -> SurrogateState | None:
    checkpoint_dir = config.workspace.surrogate_checkpoint_dir
    if not checkpoint_dir.is_dir():
        return None
    candidates = sorted(
        checkpoint_dir.glob("generation_*.json"), reverse=True
    )
    for checkpoint_path in candidates:
        try:
            return _recover_state_from_checkpoint(config, checkpoint_path)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return None


def _recover_state_from_checkpoint(
    config: LoadedConfig, checkpoint_path: Path
) -> SurrogateState:
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("surrogate checkpoint must be a JSON object")
    generation_index = int(payload["generation_index"])
    artifact_name = Path(
        str(
            payload.get(
                "artifact_dir",
                f"generation_{generation_index:04d}_conditional_inr",
            )
        )
    ).name
    artifact_dir = checkpoint_path.parent / artifact_name
    model_name = Path(str(payload.get("model_path", "model_aux.npz"))).name
    model_path = artifact_dir / model_name
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    data = _load_training_data(config.workspace)
    data, _dropped = _filter_training_data_by_nonfinite_fraction(
        data, threshold=float(config.SURROGATE_MAX_NONFINITE_FRACTION)
    )
    x = _x_matrix(data.normalized_variables)
    schema, _current_flat = _flatten_raw_samples(
        data.raw_data, constant_atol=float(config.SURROGATE_CONSTANT_ATOL)
    )
    with np.load(model_path, allow_pickle=False) as auxiliary:
        training_flat_values = np.asarray(
            auxiliary["training_flat_values"], dtype=np.float64
        )
        query_weights = np.asarray(auxiliary["query_weights"], dtype=np.float32)
        flat_dim = int(np.asarray(auxiliary["schema_flat_dim"]).item())
        target_mean = (
            np.asarray(auxiliary["target_mean"], dtype=np.float32)
            if "target_mean" in auxiliary.files
            else None
        )
        target_scale = (
            np.asarray(auxiliary["target_scale"], dtype=np.float32)
            if "target_scale" in auxiliary.files
            else None
        )
        coord_table = (
            np.asarray(auxiliary["coord_table"], dtype=np.float32)
            if "coord_table" in auxiliary.files
            else np.zeros((0, 3), dtype=np.float32)
        )
        field_ids = (
            np.asarray(auxiliary["field_ids"], dtype=np.int64)
            if "field_ids" in auxiliary.files
            else np.zeros((0,), dtype=np.int64)
        )

    if schema is None or int(schema.flat_dim) != flat_dim:
        raise ValueError("current workspace rawData schema does not match checkpoint")
    if coord_table.shape != schema.coord_table.shape or field_ids.shape != schema.field_ids.shape:
        raise ValueError("current workspace rawData queries do not match checkpoint")
    schema = RawDataSchema(
        templates=schema.templates,
        modeled_slots=schema.modeled_slots,
        flat_dim=schema.flat_dim,
        coord_table=np.ascontiguousarray(coord_table, dtype=np.float32),
        field_ids=np.ascontiguousarray(field_ids, dtype=np.int64),
    )

    train_cfg = _train_config_from_loaded_config(config)
    device = _select_device(config)
    model = None
    scaler = None
    if target_mean is not None and target_scale is not None and flat_dim > 0:
        scaler = TargetScaler(
            mean=np.ascontiguousarray(target_mean, dtype=np.float32),
            scale=np.ascontiguousarray(target_scale, dtype=np.float32),
        )
        meta_path = artifact_dir / "inr_meta.json"
        if meta_path.is_file():
            inr_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if int(inr_meta.get("input_dim", -1)) != int(x.shape[1]):
                raise ValueError(
                    "current workspace parameter width does not match checkpoint"
                )
            model, input_dim, n_fields, train_cfg = load_inr_artifacts(
                artifact_dir, device
            )
            if int(input_dim) != int(x.shape[1]):
                raise ValueError(
                    "current workspace parameter width does not match checkpoint"
                )
            if int(n_fields) != int(schema.n_fields):
                raise ValueError(
                    "current workspace rawData fields do not match checkpoint"
                )

    true_costs = (
        _costs_from_raw(config.workspace, data.raw_data) if data.raw_data else ()
    )
    state = SurrogateState(
        generation_index=generation_index,
        sample_count=int(payload.get("sample_count", len(data.normalized_variables))),
        checkpoint_path=checkpoint_path,
        model_path=model_path,
        artifact_dir=artifact_dir,
        model_name=str(payload.get("model", MODEL_NAME)),
        parameter_names=data.parameter_names,
        normalized_variables=data.normalized_variables,
        raw_data=data.raw_data,
        schema=schema,
        scaler=scaler,
        model=model,
        train_cfg=train_cfg,
        device=device,
        train_history=dict(payload.get("train_history", {})),
        training_flat_values=np.ascontiguousarray(
            training_flat_values, dtype=np.float64
        ),
        query_weights=np.ascontiguousarray(query_weights, dtype=np.float32),
        mean_relative_error=0.0,
        historical_relative_error_p50=(),
        historical_relative_error_p90=(),
        historical_relative_error_p95=(),
        historical_absolute_error_p90=(),
        historical_true_costs=true_costs,
        historical_predicted_costs=(),
    )
    predicted_costs = (
        _predict_costs_for_error_audit(config.workspace, state, x)
        if model is not None and x.shape[0] > 0
        else ()
    )
    epsilon = float(config.SURROGATE_RELATIVE_ERROR_EPS)
    relative_errors = _relative_errors(
        true_costs, predicted_costs, epsilon=epsilon
    )
    absolute_errors = _absolute_errors(true_costs, predicted_costs)
    return replace(
        state,
        mean_relative_error=_mean_relative_error(
            true_costs, predicted_costs, epsilon=epsilon
        ),
        historical_relative_error_p50=_quantile_by_objective(
            relative_errors, 0.50
        ),
        historical_relative_error_p90=_quantile_by_objective(
            relative_errors, 0.90
        ),
        historical_relative_error_p95=_quantile_by_objective(
            relative_errors, 0.95
        ),
        historical_absolute_error_p90=_quantile_by_objective(
            absolute_errors, 0.90
        ),
        historical_predicted_costs=predicted_costs,
    )

def _state_input_dim(state: SurrogateState) -> int:
    if state.normalized_variables:
        return len(state.normalized_variables[0])
    return len(state.parameter_names)


def predict_raw_data(
    workspace: WorkspaceContext | str | Path, population
) -> tuple[RawSample, ...]:
    config = load_config(workspace)
    state = _require_state(config)
    if state.schema is None or state.schema.flat_dim == 0:
        return tuple()
    x = _x_matrix(population, _state_input_dim(state))
    member_flats = _predict_member_flats(state, x)
    mean_flat = np.mean(member_flats, axis=0)
    return _raw_samples_from_flat(state.schema, mean_flat)


def predict_population(
    workspace: WorkspaceContext | str | Path, population
) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
    config = load_config(workspace)
    state = _require_state(config)
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


def evaluate_historical_errors(
    workspace: WorkspaceContext | str | Path,
) -> tuple[tuple[float, ...], ...]:
    config = load_config(workspace)
    state = _require_state(config)
    return _relative_errors(
        state.historical_true_costs,
        state.historical_predicted_costs,
        epsilon=float(config.SURROGATE_RELATIVE_ERROR_EPS),
    )
