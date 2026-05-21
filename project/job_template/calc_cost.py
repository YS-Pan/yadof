"""Dynamic rawData-to-cost calculation for the default test task."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .rawdata_contract import load_rawdata_item, metadata_from_item, validate_rawdata_item

RawDataItem = Mapping[str, object] | str | Path
OBJECTIVE_NAMES = (
    "target_match_cost",
    "curve_magnitude_cost",
    "surface_reward_cost",
)
ERROR_COSTS = (1.0, 1.0, 1.0)
CURVE_AXIS_RANGE = (0.46, 0.54)
SURFACE_AXIS_0_RANGE = (0.46, 0.54)
SURFACE_AXIS_1_RANGE = (0.46, 0.54)


def get_objective_names() -> tuple[str, ...]:
    return tuple(OBJECTIVE_NAMES)


def get_objective_count() -> int:
    return len(OBJECTIVE_NAMES)


def _soft_cost(result: float, goal: float, worst: float) -> float:
    """Map a scalar metric to a bounded minimization cost.

    This mirrors the old workflow's tanh-based cost shaping: values near the
    goal become close to 0, values near the worst threshold become close to 1.
    """

    r, goal, worst = float(result), float(goal), float(worst)
    if not (np.isfinite(r) and np.isfinite(goal) and np.isfinite(worst)) or goal == worst:
        return 1.0
    value = (np.tanh(4.0 * (r - worst) / (worst - goal) + 2.0) + 1.0) / 2.0
    return float(np.clip(value, 0.0, 1.0))


def _finite_values(values: object) -> np.ndarray:
    array = np.asarray(values, dtype=float).ravel()
    return array[np.isfinite(array)]


def _axis_window(values: np.ndarray, axis_values: object, axis: int, low: float, high: float) -> np.ndarray:
    coords = np.asarray(axis_values, dtype=float).ravel()
    if values.ndim <= axis or coords.size != values.shape[axis]:
        return values
    lo, hi = sorted((float(low), float(high)))
    mask = (coords >= lo) & (coords <= hi)
    if not np.any(mask):
        return np.asarray((), dtype=float)
    return np.take(values, np.flatnonzero(mask), axis=axis)


def _surface_observation_values(item: Mapping[str, object]) -> np.ndarray:
    values = np.asarray(item.get("values", ()), dtype=float)
    window = _axis_window(values, item.get("axis_0", ()), 0, *SURFACE_AXIS_0_RANGE)
    window = _axis_window(window, item.get("axis_1", ()), 1, *SURFACE_AXIS_1_RANGE)
    return window.ravel()


def _curve_band_values(item: Mapping[str, object], curve_index: int) -> np.ndarray:
    values = np.asarray(item.get("values", ()), dtype=float)
    if values.ndim == 0:
        return np.asarray((), dtype=float)
    if values.ndim == 1:
        return _axis_window(values, item.get("axis_0", ()), 0, *CURVE_AXIS_RANGE).ravel()
    selected_index = min(max(0, int(curve_index)), values.shape[0] - 1)
    selected_curve = np.asarray(values[selected_index], dtype=float)
    return _axis_window(selected_curve, item.get("axis_1", ()), 0, *CURVE_AXIS_RANGE).ravel()


def _mean_soft_cost(values: Sequence[float]) -> float:
    finite = [float(value) for value in values if np.isfinite(float(value))]
    return float(np.mean(finite)) if finite else 1.0


def calculate_cost(sample_rawdata: Sequence[RawDataItem]) -> tuple[float, ...]:
    """Calculate objective values for one sample from in-memory or file rawData."""

    by_name: dict[str, dict[str, object]] = {}
    for item in sample_rawdata:
        loaded = validate_rawdata_item(load_rawdata_item(item))
        name = str(metadata_from_item(loaded).get("rawdata_name") or len(by_name))
        by_name[name] = loaded

    summary_values = np.asarray(by_name.get("summary", {}).get("values", ()), dtype=float).ravel()
    curve_item = by_name.get("curve", {})
    curve0_values = _curve_band_values(curve_item, 0)
    curve1_values = _curve_band_values(curve_item, 1)
    surface_values = _surface_observation_values(by_name.get("surface", {}))

    if summary_values.size < 2 or curve0_values.size == 0 or curve1_values.size == 0 or surface_values.size == 0:
        return ERROR_COSTS

    scalar0, scalar1 = summary_values[:2]
    curve0_finite = _finite_values(curve0_values)
    curve1_finite = _finite_values(curve1_values)
    surface_finite = _finite_values(surface_values)
    if curve0_finite.size == 0 or curve1_finite.size == 0 or surface_finite.size == 0:
        return ERROR_COSTS

    scalar0_value = float(scalar0)
    scalar1_value = float(scalar1)
    curve0_band_mean = float(np.mean(curve0_finite))
    curve1_band_mean = float(np.mean(curve1_finite))
    surface_center_mean = float(np.mean(surface_finite))
    if not all(
        np.isfinite(value)
        for value in (scalar0_value, scalar1_value, curve0_band_mean, curve1_band_mean, surface_center_mean)
    ):
        return ERROR_COSTS

    return (
        _mean_soft_cost(
            (
                _soft_cost(scalar0_value, goal=0.72, worst=0.42),
                _soft_cost(scalar1_value, goal=0.28, worst=0.62),
            )
        ),
        _mean_soft_cost(
            (
                _soft_cost(curve0_band_mean, goal=0.40, worst=0.18),
                _soft_cost(curve1_band_mean, goal=0.44, worst=0.55),
            )
        ),
        _soft_cost(surface_center_mean, goal=0.40, worst=0.20),
    )


def calculate_costs(samples: Sequence[Sequence[RawDataItem]]) -> tuple[tuple[float, ...], ...]:
    return tuple(calculate_cost(sample) for sample in samples)


def _axis_mask(size: int, axis_values: object, low: float, high: float) -> np.ndarray:
    coords = np.asarray(axis_values, dtype=float).ravel()
    if coords.size != int(size):
        return np.ones((int(size),), dtype=bool)
    lo, hi = sorted((float(low), float(high)))
    return (coords >= lo) & (coords <= hi)


def rawdata_importance_weights(
    sample_rawdata: Sequence[RawDataItem],
    *,
    floor: float = 0.25,
    boost: float = 2.0,
) -> tuple[dict[str, np.ndarray], ...]:
    """Return task-owned per-rawData weights for surrogate full-field training.

    The full fields remain trainable everywhere, but the observation windows
    used by the default objectives receive extra weight.
    """

    base = max(0.0, float(floor))
    important = max(base, base + max(0.0, float(boost)))
    out: list[dict[str, np.ndarray]] = []
    for item in sample_rawdata:
        loaded = validate_rawdata_item(load_rawdata_item(item))
        metadata = metadata_from_item(loaded)
        name = str(metadata.get("rawdata_name") or "")
        values = np.asarray(loaded.get("values", ()), dtype=float)
        if values.size == 0:
            out.append({})
            continue

        weights = np.full(values.shape, base, dtype=np.float32)
        if name == "summary":
            weights[...] = important
        elif name == "curve":
            if values.ndim == 1:
                mask = _axis_mask(values.shape[0], loaded.get("axis_0", ()), *CURVE_AXIS_RANGE)
                weights[mask] = important
            elif values.ndim >= 2:
                mask = _axis_mask(values.shape[1], loaded.get("axis_1", ()), *CURVE_AXIS_RANGE)
                for curve_idx in range(min(2, values.shape[0])):
                    weights[curve_idx, mask] = important
        elif name == "surface" and values.ndim >= 2:
            mask0 = _axis_mask(values.shape[0], loaded.get("axis_0", ()), *SURFACE_AXIS_0_RANGE)
            mask1 = _axis_mask(values.shape[1], loaded.get("axis_1", ()), *SURFACE_AXIS_1_RANGE)
            weights[np.ix_(mask0, mask1)] = important
        out.append({"values": weights})
    return tuple(out)
