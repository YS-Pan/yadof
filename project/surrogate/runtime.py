from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from project import config


Population = tuple[tuple[float, ...], ...]
RawDataItem = Mapping[str, object] | str | Path
RawSample = tuple[RawDataItem, ...]


@dataclass(frozen=True)
class TrainingData:
    parameter_names: tuple[str, ...]
    normalized_variables: Population
    raw_data: tuple[RawSample, ...]


@dataclass(frozen=True)
class RawArraySlot:
    item_index: int
    key: str
    shape: tuple[int, ...]
    dtype: str
    start: int
    end: int


@dataclass(frozen=True)
class RawDataSchema:
    templates: tuple[dict[str, object], ...]
    modeled_slots: tuple[RawArraySlot, ...]
    flat_dim: int


@dataclass(frozen=True)
class RbfMember:
    length_scale: float
    centers: np.ndarray
    weights: np.ndarray


@dataclass(frozen=True)
class IdwMember:
    power: float
    centers: np.ndarray
    values: np.ndarray


ModelMember = RbfMember | IdwMember


@dataclass(frozen=True)
class SurrogateModel:
    input_dim: int
    members: tuple[ModelMember, ...]


@dataclass(frozen=True)
class SurrogateState:
    generation_index: int
    sample_count: int
    checkpoint_path: Path
    model_path: Path
    parameter_names: tuple[str, ...]
    normalized_variables: Population
    raw_data: tuple[RawSample, ...]
    schema: RawDataSchema | None
    model: SurrogateModel | None
    mean_relative_error: float
    historical_true_costs: tuple[tuple[float, ...], ...]
    historical_predicted_costs: tuple[tuple[float, ...], ...]


_STATE: SurrogateState | None = None


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


def _load_training_data() -> TrainingData:
    recorded_api = importlib.import_module("project.recorded_data.api")
    bundled = None
    try:
        bundled = _call_first(
            recorded_api,
            ("get_surrogate_training_data", "get_training_data_for_surrogate"),
        )
    except AttributeError:
        bundled = None

    if bundled is not None:
        if isinstance(bundled, dict):
            names = bundled.get("parameter_names", ())
            variables = bundled.get("normalized_variables", ())
            raw_data = bundled.get("raw_data", bundled.get("rawData", ()))
        else:
            names, variables, raw_data = bundled
        return TrainingData(
            tuple(str(name) for name in names),
            _as_population(variables),
            _as_raw_samples(raw_data),
        )

    try:
        names, variables = _call_first(recorded_api, ("get_normalized_variable_table",))
    except AttributeError:
        rows = _call_first(
            recorded_api,
            ("get_normalized_variables", "get_normalized_variable_values"),
        )
        names = ()
        variables = tuple(values for _job_name, values in rows)

    try:
        raw_rows = _call_first(recorded_api, ("get_rawdata_samples",))
        raw_data = tuple(rawdata for _job_name, rawdata in raw_rows)
    except AttributeError:
        raw_data = _call_first(recorded_api, ("get_raw_data", "get_rawData"))

    return TrainingData(
        tuple(str(name) for name in names),
        _as_population(variables),
        _as_raw_samples(raw_data),
    )


def _costs_from_raw(raw_samples: Sequence[Sequence[RawDataItem]]) -> tuple[tuple[float, ...], ...]:
    job_template_api = importlib.import_module("project.job_template.api")
    raw_costs = _call_first(
        job_template_api,
        (
            "calculate_costs_from_raw_data",
            "calc_costs_from_raw_data",
            "calculate_costs",
            "calc_costs",
            "calculate_cost",
        ),
        tuple(tuple(sample) for sample in raw_samples),
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


def _normalize_samples(raw_samples: tuple[RawSample, ...]) -> tuple[tuple[dict[str, object], ...], ...]:
    return tuple(tuple(_load_rawdata_item(item) for item in sample) for sample in raw_samples)


def _flatten_raw_samples(
    raw_samples: tuple[RawSample, ...],
) -> tuple[RawDataSchema | None, np.ndarray]:
    samples = _normalize_samples(raw_samples)
    if not samples:
        return None, np.zeros((0, 0), dtype=np.float64)

    item_count = len(samples[0])
    if item_count == 0:
        return RawDataSchema(templates=(), modeled_slots=(), flat_dim=0), np.zeros((len(samples), 0), dtype=np.float64)
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
    atol = float(getattr(config, "SURROGATE_CONSTANT_ATOL", 1e-12))

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

            matrix = np.stack([array.reshape(-1) for array in arrays], axis=0)
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
                )
            )
            columns.append(matrix)

    y = np.concatenate(columns, axis=1).astype(np.float64) if columns else np.zeros((len(samples), 0), dtype=np.float64)
    schema = RawDataSchema(templates=templates, modeled_slots=tuple(modeled_slots), flat_dim=int(y.shape[1]))
    return schema, np.ascontiguousarray(y, dtype=np.float64)


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
                metadata["source"] = "project.surrogate.runtime"
                metadata["surrogate_prediction"] = True
                metadata.pop("variables", None)
                item["metadata"] = _metadata_array(metadata)

        samples.append(tuple(mutable_items))
    return tuple(samples)


def _x_matrix(population: Population | Sequence[Sequence[float]], input_dim: int | None = None) -> np.ndarray:
    rows = _as_population(population)
    if not rows:
        width = 0 if input_dim is None else int(input_dim)
        return np.zeros((0, width), dtype=np.float64)
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("population must be a two-dimensional sequence")
    if input_dim is not None and matrix.shape[1] != int(input_dim):
        raise ValueError(f"expected population width {int(input_dim)}, got {matrix.shape[1]}")
    return np.ascontiguousarray(np.clip(matrix, 0.0, 1.0), dtype=np.float64)


def _pairwise_squared(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    left = np.ascontiguousarray(left, dtype=np.float64)
    right = np.ascontiguousarray(right, dtype=np.float64)
    diff = left[:, None, :] - right[None, :, :]
    return np.sum(diff * diff, axis=2)


def _median_pair_distance(x: np.ndarray) -> float:
    if x.shape[0] < 2:
        return 1.0
    dist = np.sqrt(_pairwise_squared(x, x))
    values = dist[np.triu_indices(x.shape[0], k=1)]
    values = values[np.isfinite(values) & (values > 0.0)]
    if values.size == 0:
        return max(1.0, math.sqrt(max(1, x.shape[1])))
    return float(np.median(values))


def _fit_model(x: np.ndarray, y: np.ndarray) -> SurrogateModel | None:
    x = np.ascontiguousarray(x, dtype=np.float64)
    y = np.ascontiguousarray(y, dtype=np.float64)
    if x.ndim != 2 or y.ndim != 2 or x.shape[0] != y.shape[0]:
        raise ValueError("surrogate model fit requires X[N,D] and Y[N,Q]")
    input_dim = int(x.shape[1]) if x.ndim == 2 else 0
    if x.shape[0] == 0 or y.shape[1] == 0:
        return None

    members: list[ModelMember] = []
    if x.shape[0] >= 2:
        base = max(_median_pair_distance(x), 1e-6)
        ridge = float(getattr(config, "SURROGATE_RBF_RIDGE", 1e-8))
        for factor in (0.5, 1.0, 2.0):
            length_scale = base * factor
            kernel = np.exp(-0.5 * _pairwise_squared(x, x) / (length_scale * length_scale))
            kernel.flat[:: kernel.shape[0] + 1] += ridge
            try:
                weights = np.linalg.solve(kernel, y)
            except np.linalg.LinAlgError:
                weights = np.linalg.lstsq(kernel, y, rcond=None)[0]
            members.append(
                RbfMember(
                    length_scale=float(length_scale),
                    centers=x.copy(),
                    weights=np.ascontiguousarray(weights, dtype=np.float64),
                )
            )

    members.append(
        IdwMember(
            power=float(getattr(config, "SURROGATE_IDW_POWER", 2.0)),
            centers=x.copy(),
            values=y.copy(),
        )
    )
    return SurrogateModel(input_dim=input_dim, members=tuple(members))


def _predict_rbf(member: RbfMember, x: np.ndarray) -> np.ndarray:
    scale = max(float(member.length_scale), 1e-12)
    kernel = np.exp(-0.5 * _pairwise_squared(x, member.centers) / (scale * scale))
    return np.ascontiguousarray(kernel @ member.weights, dtype=np.float64)


def _predict_idw(member: IdwMember, x: np.ndarray) -> np.ndarray:
    dist = np.sqrt(_pairwise_squared(x, member.centers))
    out = np.empty((x.shape[0], member.values.shape[1]), dtype=np.float64)
    for idx, distances in enumerate(dist):
        exact = np.flatnonzero(distances <= 1e-12)
        if exact.size:
            out[idx] = member.values[int(exact[0])]
            continue
        weights = 1.0 / np.maximum(distances, 1e-12) ** max(float(member.power), 1e-12)
        weights = weights / np.sum(weights)
        out[idx] = weights @ member.values
    return out


def _predict_member_flats(model: SurrogateModel | None, x: np.ndarray, flat_dim: int) -> np.ndarray:
    if model is None or not model.members or flat_dim == 0:
        return np.zeros((1, x.shape[0], flat_dim), dtype=np.float64)
    predictions = []
    for member in model.members:
        if isinstance(member, RbfMember):
            predictions.append(_predict_rbf(member, x))
        else:
            predictions.append(_predict_idw(member, x))
    return np.stack(predictions, axis=0).astype(np.float64)


def _snap_to_exact_neighbors(
    x: np.ndarray,
    y_pred: np.ndarray,
    x_train: Population,
    raw_train: tuple[RawSample, ...],
    schema: RawDataSchema | None,
) -> np.ndarray:
    if schema is None or not x_train or not raw_train or y_pred.size == 0:
        return y_pred
    radius = float(getattr(config, "SURROGATE_EXACT_NEIGHBOR_RADIUS", 0.0))
    if radius <= 0.0:
        return y_pred

    train_x = _x_matrix(x_train)
    _train_schema, train_y = _flatten_raw_samples(raw_train)
    if train_y.shape[0] != train_x.shape[0] or train_y.shape[1] != y_pred.shape[1]:
        return y_pred

    snapped = np.ascontiguousarray(y_pred, dtype=np.float64).copy()
    distances = np.sqrt(_pairwise_squared(np.ascontiguousarray(x, dtype=np.float64), train_x))
    for row_idx, row_distances in enumerate(distances):
        nearest_idx = int(np.argmin(row_distances))
        if float(row_distances[nearest_idx]) <= radius:
            snapped[row_idx] = train_y[nearest_idx]
    return snapped


def _relative_errors(true_costs, pred_costs) -> tuple[tuple[float, ...], ...]:
    rows = []
    for true_row, pred_row in zip(true_costs, pred_costs):
        row = []
        for true_value, pred_value in zip(true_row, pred_row):
            denom = max(abs(float(true_value)), float(config.SURROGATE_RELATIVE_ERROR_EPS))
            row.append(abs(float(pred_value) - float(true_value)) / denom)
        rows.append(tuple(row))
    return tuple(rows)


def _mean_relative_error(true_costs, pred_costs) -> float:
    values = [value for row in _relative_errors(true_costs, pred_costs) for value in row if math.isfinite(value)]
    return float(sum(values) / len(values)) if values else 0.0


def _cross_validated_costs(
    x: np.ndarray,
    y: np.ndarray,
    schema: RawDataSchema | None,
    true_costs: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    if x.shape[0] <= 1 or schema is None:
        return true_costs

    predictions: list[tuple[float, ...]] = []
    for idx in range(x.shape[0]):
        mask = np.ones((x.shape[0],), dtype=bool)
        mask[idx] = False
        try:
            model = _fit_model(x[mask], y[mask])
            member_flats = _predict_member_flats(model, x[idx : idx + 1], y.shape[1])
            mean_flat = np.mean(member_flats, axis=0)
            raw = _raw_samples_from_flat(schema, mean_flat)
            predictions.append(_costs_from_raw(raw)[0])
        except Exception:
            nearest = int(np.argmin(np.sum((x[mask] - x[idx]) ** 2, axis=1)))
            predictions.append(true_costs[nearest])
    return tuple(predictions)


def _schema_payload(schema: RawDataSchema | None) -> dict[str, object]:
    if schema is None:
        return {"flat_dim": 0, "modeled_slots": []}
    return {
        "rawdata_item_count": len(schema.templates),
        "flat_dim": int(schema.flat_dim),
        "modeled_slots": [
            {
                "item_index": int(slot.item_index),
                "key": slot.key,
                "shape": list(slot.shape),
                "dtype": slot.dtype,
                "start": int(slot.start),
                "end": int(slot.end),
            }
            for slot in schema.modeled_slots
        ],
    }


def _write_checkpoint(state: SurrogateState) -> None:
    state.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generation_index": int(state.generation_index),
        "sample_count": int(state.sample_count),
        "parameter_names": list(state.parameter_names),
        "model": "rbf_idw_rawdata_ensemble",
        "member_count": 0 if state.model is None else len(state.model.members),
        "mean_relative_error": float(state.mean_relative_error),
        "model_path": state.model_path.name,
        "schema": _schema_payload(state.schema),
        "note": "Surrogate predicts rawData arrays; costs are dynamically derived through job_template.calc_cost.",
    }
    state.checkpoint_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )

    arrays: dict[str, np.ndarray] = {
        "schema_flat_dim": np.asarray(0 if state.schema is None else state.schema.flat_dim, dtype=np.int64),
        "training_sample_count": np.asarray(state.sample_count, dtype=np.int64),
    }
    if state.model is not None:
        for idx, member in enumerate(state.model.members):
            if isinstance(member, RbfMember):
                arrays[f"member_{idx:03d}_centers"] = member.centers
                arrays[f"member_{idx:03d}_weights"] = member.weights
                arrays[f"member_{idx:03d}_kind"] = np.asarray("rbf")
                arrays[f"member_{idx:03d}_length_scale"] = np.asarray(member.length_scale, dtype=np.float64)
            else:
                arrays[f"member_{idx:03d}_centers"] = member.centers
                arrays[f"member_{idx:03d}_values"] = member.values
                arrays[f"member_{idx:03d}_kind"] = np.asarray("idw")
                arrays[f"member_{idx:03d}_power"] = np.asarray(member.power, dtype=np.float64)
    np.savez_compressed(state.model_path, **arrays)


def train(*, generation_index: int = 0) -> SurrogateState:
    global _STATE

    data = _load_training_data()
    if len(data.normalized_variables) != len(data.raw_data):
        raise ValueError("surrogate training needs one rawData sample per normalized variable row")

    x = _x_matrix(data.normalized_variables)
    schema, y = _flatten_raw_samples(data.raw_data)
    model = _fit_model(x, y) if x.shape[0] and y.shape[1] else None
    true_costs = _costs_from_raw(data.raw_data) if data.raw_data else ()
    cv_pred_costs = _cross_validated_costs(x, y, schema, true_costs) if data.raw_data else ()
    mean_error = _mean_relative_error(true_costs, cv_pred_costs)

    if data.raw_data and schema is not None:
        member_flats = _predict_member_flats(model, x, schema.flat_dim)
        mean_flat = np.mean(member_flats, axis=0)
        mean_flat = _snap_to_exact_neighbors(x, mean_flat, data.normalized_variables, data.raw_data, schema)
        pred_costs = _costs_from_raw(_raw_samples_from_flat(schema, mean_flat))
    else:
        pred_costs = true_costs

    checkpoint_path = Path(config.SURROGATE_CHECKPOINT_DIR) / f"generation_{int(generation_index):04d}.json"
    state = SurrogateState(
        generation_index=int(generation_index),
        sample_count=len(data.normalized_variables),
        checkpoint_path=checkpoint_path,
        model_path=checkpoint_path.with_suffix(".npz"),
        parameter_names=data.parameter_names,
        normalized_variables=data.normalized_variables,
        raw_data=data.raw_data,
        schema=schema,
        model=model,
        mean_relative_error=float(mean_error),
        historical_true_costs=true_costs,
        historical_predicted_costs=pred_costs,
    )
    _write_checkpoint(state)
    _STATE = state
    return state


def _ensure_state() -> SurrogateState:
    global _STATE
    if _STATE is None:
        _STATE = train(generation_index=0)
    return _STATE


def predict_raw_data(population) -> tuple[RawSample, ...]:
    state = _ensure_state()
    if state.schema is None:
        return tuple()
    x = _x_matrix(population, state.model.input_dim if state.model is not None else None)
    member_flats = _predict_member_flats(state.model, x, state.schema.flat_dim)
    mean_flat = np.mean(member_flats, axis=0)
    mean_flat = _snap_to_exact_neighbors(x, mean_flat, state.normalized_variables, state.raw_data, state.schema)
    return _raw_samples_from_flat(state.schema, mean_flat)


def predict_population(population) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
    state = _ensure_state()
    normalized_population = _as_population(population)
    if not normalized_population:
        return ()
    if state.schema is None:
        costs = tuple((float("inf"),) for _ in normalized_population)
        return tuple((row, tuple((value, value) for value in row)) for row in costs)

    x = _x_matrix(normalized_population, state.model.input_dim if state.model is not None else None)
    member_flats = _predict_member_flats(state.model, x, state.schema.flat_dim)
    mean_flat = np.mean(member_flats, axis=0)
    mean_flat = _snap_to_exact_neighbors(x, mean_flat, state.normalized_variables, state.raw_data, state.schema)
    predicted_raw = _raw_samples_from_flat(state.schema, mean_flat)
    costs = _costs_from_raw(predicted_raw)

    member_costs = []
    for member_idx in range(member_flats.shape[0]):
        try:
            member_raw = _raw_samples_from_flat(state.schema, member_flats[member_idx])
            member_costs.append(np.asarray(_costs_from_raw(member_raw), dtype=np.float64))
        except Exception:
            continue
    cost_std = (
        np.std(np.stack(member_costs, axis=0), axis=0)
        if member_costs
        else np.zeros((len(costs), len(costs[0]) if costs else 0), dtype=np.float64)
    )

    relative_width = max(float(config.SURROGATE_ALPHA), float(state.mean_relative_error))
    out = []
    for row_idx, cost_row in enumerate(costs):
        intervals = []
        for cost_idx, value in enumerate(cost_row):
            std = float(cost_std[row_idx, cost_idx]) if cost_std.size else 0.0
            delta = max(std, abs(float(value)) * relative_width, relative_width)
            intervals.append((float(value) - delta, float(value) + delta))
        out.append((tuple(float(value) for value in cost_row), tuple(intervals)))
    return tuple(out)


def evaluate_historical_errors() -> tuple[tuple[float, ...], ...]:
    state = _ensure_state()
    return _relative_errors(state.historical_true_costs, state.historical_predicted_costs)
