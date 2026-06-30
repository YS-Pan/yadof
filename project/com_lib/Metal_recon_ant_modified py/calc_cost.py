"""Dynamic rawData-to-cost calculation for the Metal_recon_ant HFSS task."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from . import parameters_constraints as parameter_config
from .rawdata_contract import load_rawdata_item, metadata_from_item, validate_rawdata_item

RawDataItem = Mapping[str, object] | str | Path
RawVariables = Mapping[str, float] | Sequence[float]
SIMULATION_OBJECTIVE_NAMES = (
    "cost_s11_band",
    "cost_gain_steering",
    "cost_gain_split",
    "cost_gain_broadside",
)
ERROR_COST = 1.0

PIN_STATES = (1, 2, 3, 4)
S11_BAND_GHZ = (2.40, 2.48)
TARGET_FREQ_GHZ = 2.44
TARGET_PHI_DEG = 90.0
TARGET_THETA_DEG = (-30, 0, 30)
ANGLE_TOL_DEG = 1.5
FREQ_TOL_GHZ = 0.02

SOFTMAX_EDGE_COST = 0.1
SOFTMAX_TANH_SLOPE = None
CONSTRAINT_SOFTMAX_EDGE_COST = SOFTMAX_EDGE_COST
CONSTRAINT_SOFTMAX_TANH_SLOPE = SOFTMAX_TANH_SLOPE

_PIN_STATE_RE = re.compile(r"pinState(\d+)", re.IGNORECASE)
_DOLLAR_VAR_RE = re.compile(r"\$([A-Za-z_]\w*)")


def get_objective_names() -> tuple[str, ...]:
    return SIMULATION_OBJECTIVE_NAMES + (("cost_constraints",) if _constraint_expressions() else ())


def get_objective_count() -> int:
    return len(get_objective_names())


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
    """Calculate objective values for one sample from in-memory or file rawData."""

    loaded_items = tuple(validate_rawdata_item(load_rawdata_item(item)) for item in sample_rawdata)
    s11_items = tuple(item for item in loaded_items if _rawdata_name(item).startswith("s11"))
    gain_by_state = {
        state: item
        for item in loaded_items
        if _rawdata_name(item).startswith("gain") and (state := _pin_state(item)) is not None
    }
    if not s11_items or any(state not in gain_by_state for state in PIN_STATES):
        return _error_costs()

    try:
        measured = {
            "s11_band_value": _s11_band_value(s11_items),
            "gain": {state: _gain_cut(gain_by_state[state]) for state in PIN_STATES},
        }
        costs = (
            _objective_s11(measured),
            _objective_gain_steering(measured),
            _objective_gain_split(measured),
            _objective_gain_broadside(measured),
        )
    except (KeyError, ValueError, IndexError, TypeError, FloatingPointError):
        return _error_costs()
    if not _constraint_expressions():
        return costs
    try:
        return costs + (_constraint_cost(raw_variables),)
    except (KeyError, ValueError, IndexError, TypeError, FloatingPointError, NameError, SyntaxError):
        return costs + (ERROR_COST,)


def calculate_costs(
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    sample_rows = tuple(samples)
    variable_rows = (None,) * len(sample_rows) if raw_variables is None else tuple(raw_variables)
    if len(variable_rows) != len(sample_rows):
        raise ValueError(f"expected {len(sample_rows)} variable rows, got {len(variable_rows)}")
    return tuple(calculate_cost(sample, variables) for sample, variables in zip(sample_rows, variable_rows))


def _rawdata_name(item: Mapping[str, object]) -> str:
    return str(metadata_from_item(item).get("rawdata_name") or "")


def _pin_state(item: Mapping[str, object]) -> int | None:
    metadata = metadata_from_item(item)
    raw = metadata.get("pin_state")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        match = _PIN_STATE_RE.search(_rawdata_name(item))
        return int(match.group(1)) if match else None


def _data_array(item: Mapping[str, object]) -> np.ndarray:
    key = "data" if "data" in item else "values"
    return np.asarray(item.get(key, ()), dtype=float)


def _scalar_text(value: object) -> str:
    array = np.asarray(value)
    if array.shape == ():
        return str(array.item())
    return str(value)


def _axis_names(item: Mapping[str, object]) -> list[str]:
    metadata = metadata_from_item(item)
    raw_names = metadata.get("axis_names")
    if isinstance(raw_names, Sequence) and not isinstance(raw_names, (str, bytes, Mapping)):
        return [str(name) for name in raw_names]
    raw_axes = metadata.get("axes")
    names: list[str] = []
    if isinstance(raw_axes, Sequence) and not isinstance(raw_axes, (str, bytes, Mapping)):
        for descriptor in raw_axes:
            if isinstance(descriptor, Mapping):
                name = descriptor.get("name")
                if name is None and isinstance(descriptor.get("values_key"), str):
                    name = str(descriptor["values_key"]).removeprefix("axis_")
                names.append(str(name if name is not None else len(names)))
            else:
                names.append(str(descriptor))
    return names


def _load_axis(item: Mapping[str, object], name: str) -> tuple[np.ndarray, str]:
    values = np.asarray(item.get(f"axis_{name}", ()), dtype=float).ravel()
    unit = _scalar_text(item.get(f"unit_{name}", ""))
    return values, unit


def _freq_to_ghz(values: np.ndarray, unit: str) -> np.ndarray:
    scale = {"hz": 1e-9, "khz": 1e-6, "mhz": 1e-3, "ghz": 1.0}.get(unit.strip().lower())
    if scale is not None:
        return values * scale
    vmax = float(np.max(np.abs(values))) if values.size else 0.0
    return values * (1e-9 if vmax > 1e8 else 1e-6 if vmax > 1e5 else 1e-3 if vmax > 1e2 else 1.0)


def _angle_to_deg(values: np.ndarray, unit: str) -> np.ndarray:
    unit_text = unit.strip().lower()
    if unit_text.startswith("rad") or (not unit_text and values.size and float(np.max(np.abs(values))) <= 2.0 * np.pi + 1e-9):
        return np.degrees(values)
    return values


def _nearest_index(values: np.ndarray, target: float, tol: float, *, period: float | None = None) -> int:
    vals = np.asarray(values, dtype=float).ravel()
    if vals.size == 0:
        raise ValueError("empty axis")
    diff = vals - float(target)
    if period is not None:
        p = abs(float(period))
        diff = np.minimum.reduce((np.abs(diff), np.abs(diff - p), np.abs(diff + p)))
    else:
        diff = np.abs(diff)
    idx = int(np.argmin(diff))
    if float(diff[idx]) > float(tol):
        raise ValueError("nearest axis point outside tolerance")
    return idx


def _take_axis(
    data: np.ndarray,
    axes: list[str],
    name: str,
    axis_values: np.ndarray,
    target: float,
    tol: float,
    *,
    period: float | None = None,
) -> tuple[np.ndarray, list[str]]:
    if name not in axes:
        return data, axes
    axis = axes.index(name)
    if data.ndim <= axis:
        raise ValueError("axis index outside data rank")
    idx = _nearest_index(axis_values, target, tol, period=period)
    return np.take(data, idx, axis=axis), axes[:axis] + axes[axis + 1 :]


def _s11_band_value(items: Sequence[Mapping[str, object]]) -> float:
    chunks: list[np.ndarray] = []
    for item in items:
        data = _data_array(item)
        data = (np.real(data) if np.iscomplexobj(data) else data).astype(float, copy=False).ravel()
        freq, unit = _load_axis(item, "Freq")
        if freq.size == data.size:
            freq = _freq_to_ghz(freq, unit)
            lo, hi = sorted(S11_BAND_GHZ)
            values = data[(freq >= lo) & (freq <= hi)]
        else:
            values = data
        finite = values[np.isfinite(values)]
        if finite.size:
            chunks.append(finite)
    if not chunks:
        raise ValueError("no S11 data in target band")
    values = np.concatenate(chunks)
    return 0.8 * float(values.mean()) + 0.2 * float(values.max())


def _gain_cut(item: Mapping[str, object]) -> dict[int, float]:
    data = _data_array(item)
    data = (np.real(data) if np.iscomplexobj(data) else data).astype(float, copy=False)
    axes = _axis_names(item)

    if "Freq" in axes:
        freq, unit = _load_axis(item, "Freq")
        data, axes = _take_axis(data, axes, "Freq", _freq_to_ghz(freq, unit), TARGET_FREQ_GHZ, FREQ_TOL_GHZ)

    if "Phi" in axes:
        phi, unit = _load_axis(item, "Phi")
        data, axes = _take_axis(data, axes, "Phi", _angle_to_deg(phi, unit), TARGET_PHI_DEG, ANGLE_TOL_DEG, period=360.0)

    if "Theta" not in axes:
        values = np.asarray(data, dtype=float).ravel()
        if values.size == len(TARGET_THETA_DEG):
            return {int(angle): float(value) for angle, value in zip(TARGET_THETA_DEG, values)}
        raise KeyError("Theta")

    theta, unit = _load_axis(item, "Theta")
    theta = _angle_to_deg(theta, unit)
    axis = axes.index("Theta")
    return {
        int(angle): float(np.asarray(np.take(data, _nearest_index(theta, angle, ANGLE_TOL_DEG, period=360.0), axis=axis)).squeeze())
        for angle in TARGET_THETA_DEG
    }


def _mean_cost(values: Sequence[float]) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return float(np.mean(finite)) if finite else 1.0


def _soft_cost(
    result: float,
    goal: float,
    worst: float,
    *,
    error_cost: float = ERROR_COST,
    edge_cost: float | None = None,
    tanh_slope: float | None = None,
) -> float:
    if result is False or result is None:
        return float(error_cost)
    value, goal, worst = float(result), float(goal), float(worst)
    edge = float(SOFTMAX_EDGE_COST if edge_cost is None else edge_cost)
    slope = (
        2.0 * math.atanh(1.0 - 2.0 * edge)
        if tanh_slope is None and SOFTMAX_TANH_SLOPE is None
        else float(SOFTMAX_TANH_SLOPE if tanh_slope is None else tanh_slope)
    )
    if (
        not (math.isfinite(value) and math.isfinite(goal) and math.isfinite(worst))
        or goal == worst
        or not (0.0 < edge < 0.5)
        or not (math.isfinite(slope) and slope > 0.0)
    ):
        return float(error_cost)
    u = (value - goal) / (worst - goal)
    return float((math.tanh(slope * (u - 0.5)) + 1.0) / 2.0)


def _cost_ge(value: float, goal: float, margin: float) -> float:
    return _soft_cost(value, goal=goal, worst=goal - abs(float(margin)))


def _cost_le(value: float, goal: float, margin: float) -> float:
    return _soft_cost(value, goal=goal, worst=goal + abs(float(margin)))


def _objective_s11(measured: Mapping[str, object]) -> float:
    return _soft_cost(float(measured["s11_band_value"]), goal=-12.0, worst=-3.0)


def _objective_gain_steering(measured: Mapping[str, object]) -> float:
    gain = measured["gain"]  # type: ignore[index]
    g1, g2 = gain[1], gain[2]
    c1 = _mean_cost(
        (
            _cost_ge(g1[-30], 7.0, 5.0),
            _cost_le(g1[30], 0.0, 5.0),
            _soft_cost(g1[-30] - g1[30], goal=3.0, worst=0.0),
        )
    )
    c2 = _mean_cost(
        (
            _cost_le(g2[-30], 0.0, 5.0),
            _cost_ge(g2[30], 7.0, 5.0),
            _soft_cost(g2[30] - g2[-30], goal=3.0, worst=0.0),
        )
    )
    return 0.5 * (c1 + c2)


def _objective_gain_split(measured: Mapping[str, object]) -> float:
    gain = measured["gain"]  # type: ignore[index]
    g = gain[3]
    return _mean_cost(
        (
            _cost_ge(g[-30], 7.0, 5.0),
            _cost_le(g[0], -15.0, 7.0),
            _cost_ge(g[30], 7.0, 5.0),
            _soft_cost(min(g[-30], g[30]) - g[0], goal=15.0, worst=5.0),
        )
    )


def _objective_gain_broadside(measured: Mapping[str, object]) -> float:
    gain = measured["gain"]  # type: ignore[index]
    return _cost_ge(gain[4][0], 8.0, 5.0)


def _constraint_cost(raw_variables: RawVariables | None) -> float:
    constraints = _constraint_expressions()
    if not constraints:
        return 0.0
    if raw_variables is None:
        return ERROR_COST

    parameters = parameter_config.get_parameters()
    if isinstance(raw_variables, Mapping):
        values = {str(name): float(value) for name, value in raw_variables.items()}
    else:
        raw_values = tuple(float(value) for value in raw_variables)
        if len(raw_values) != len(parameters):
            raise ValueError(f"expected {len(parameters)} variables, got {len(raw_values)}")
        values = {parameter.name: value for parameter, value in zip(parameters, raw_values)}

    scope = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    scope.update({"abs": abs, "min": min, "max": max, "pow": pow, "round": round})
    scope.update(
        {
            name: value
            for name, value in vars(parameter_config).items()
            if not name.startswith("_") and isinstance(value, (int, float, bool))
        }
    )
    scope.update(values)
    scope["__get_var__"] = lambda name: float(scope[name] if name in scope else scope[f"${name}"])

    violations = [
        min(0.0, float(eval(_normalize_constraint_expr(expression), {"__builtins__": {}}, scope)))
        for expression in constraints
    ]
    return float(
        np.mean(
            [
                _soft_cost(
                    value,
                    goal=0.0,
                    worst=-1.0,
                    edge_cost=CONSTRAINT_SOFTMAX_EDGE_COST,
                    tanh_slope=CONSTRAINT_SOFTMAX_TANH_SLOPE,
                )
                for value in violations
            ]
        )
    )


def _normalize_constraint_expr(expression: str) -> str:
    return _DOLLAR_VAR_RE.sub(
        lambda match: f"__get_var__({match.group(1)!r})",
        expression.replace("^", "**"),
    )


def _constraint_expressions() -> tuple[str, ...]:
    return tuple(
        expression
        for expression in getattr(parameter_config, "CONSTRAINTS", ())
        if isinstance(expression, str) and expression.strip()
    )


def _error_costs() -> tuple[float, ...]:
    return (ERROR_COST,) * get_objective_count()


def rawdata_importance_weights(
    sample_rawdata: Sequence[RawDataItem],
    *,
    floor: float = 0.25,
    boost: float = 2.0,
) -> tuple[dict[str, np.ndarray], ...]:
    """Return task-owned per-rawData weights for surrogate full-field training."""

    base = max(0.0, float(floor))
    important = max(base, base + max(0.0, float(boost)))
    out: list[dict[str, np.ndarray]] = []
    for item in sample_rawdata:
        loaded = validate_rawdata_item(load_rawdata_item(item))
        name = _rawdata_name(loaded)
        data_key = "data" if "data" in loaded else "values"
        values = np.asarray(loaded.get(data_key, ()), dtype=float)
        if values.size == 0:
            out.append({})
            continue
        weights = np.full(values.shape, base, dtype=np.float32)
        if name.startswith("s11"):
            _mark_axis_window(weights, loaded, "Freq", S11_BAND_GHZ[0], S11_BAND_GHZ[1], important, converter=_freq_to_ghz)
        elif name.startswith("gain"):
            _mark_axis_points(weights, loaded, "Theta", TARGET_THETA_DEG, ANGLE_TOL_DEG, important, converter=_angle_to_deg)
        out.append({data_key: weights})
    return tuple(out)


def _mark_axis_window(
    weights: np.ndarray,
    item: Mapping[str, object],
    axis_name: str,
    low: float,
    high: float,
    value: float,
    *,
    converter,
) -> None:
    axes = _axis_names(item)
    if axis_name not in axes:
        weights[...] = value
        return
    axis = axes.index(axis_name)
    coords, unit = _load_axis(item, axis_name)
    coords = converter(coords, unit)
    if coords.size != weights.shape[axis]:
        weights[...] = value
        return
    lo, hi = sorted((float(low), float(high)))
    mask = (coords >= lo) & (coords <= hi)
    if np.any(mask):
        slicer = [slice(None)] * weights.ndim
        slicer[axis] = mask
        weights[tuple(slicer)] = value


def _mark_axis_points(
    weights: np.ndarray,
    item: Mapping[str, object],
    axis_name: str,
    targets: Sequence[float],
    tol: float,
    value: float,
    *,
    converter,
) -> None:
    axes = _axis_names(item)
    if axis_name not in axes:
        if weights.size == len(targets):
            weights[...] = value
        return
    axis = axes.index(axis_name)
    coords, unit = _load_axis(item, axis_name)
    coords = converter(coords, unit)
    if coords.size != weights.shape[axis]:
        return
    indices: list[int] = []
    for target in targets:
        try:
            indices.append(_nearest_index(coords, float(target), tol, period=360.0))
        except ValueError:
            continue
    if indices:
        slicer = [slice(None)] * weights.ndim
        slicer[axis] = np.asarray(sorted(set(indices)), dtype=int)
        weights[tuple(slicer)] = value
