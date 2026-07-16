"""Dynamic rawData-to-cost calculation for the Newchoke HFSS task."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import numpy as np

from . import parameters_constraints as parameter_config
from .cost_misc import (
    ALL,
    CONSTRAINT_CALCULATION_ERRORS,
    COST_CALCULATION_ERRORS,
    RawVariables,
    calculate_2d_curve_cost,
    calculate_defined_costs,
    constraint_cost,
    constraint_expressions,
    error_costs,
)
from .rawdata_contract import (
    RawDataItem,
    RawDataView,
    angle_to_degrees,
    frequency_to_ghz,
    load_rawdata_views,
    mark_axis_range,
)


ERROR_COST = 1.1
PIN_STATES = (1, 2, 3)
TARGET_PHI_DEG = 90.0
TARGET_FREQ_GHZ = 2.44
ANGLE_TOL_DEG = 1.5
FREQ_TOL_GHZ = 0.02
GAIN_COVERAGE_RANGE_DEG = (-60.0, 60.0)
BACK_LOBE_RANGES_DEG = ((-180.0, -150.0), (150.0, 180.0))

COST_CURVE = {"error_cost": ERROR_COST, "edge_cost": 0.1, "tanh_slope": None}
CONSTRAINT_COST_CURVE = dict(COST_CURVE)

COST_DEFINITIONS = (
    {
        "name": "cost_s11_band",
        "value_for_cost": "s11_by_state",
        "goal": -12.0,
        "worst": -3.0,
        "ext_ratio": 0.2,
        "data_range": (ALL, 0),
        "calculator": "calculate_s11_band_cost",
    },
    {
        "name": "cost_gain_lhcp_envelope",
        "value_for_cost": "gain_envelope",
        "goal": 7.0,
        "worst": 0.0,
        "ext_ratio": 0.7,
        "data_range": GAIN_COVERAGE_RANGE_DEG,
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "cost_peak_gain",
        "value_for_cost": "peak_gain",
        "goal": 7.0,
        "worst": 0.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "cost_back_lobe",
        "value_for_cost": "back_lobe_gain",
        "goal": -5.0,
        "worst": 5.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "cost_axial_ratio_working_direction",
        "value_for_cost": "axial_ratio_by_state",
        "goal": 0.0,
        "worst": 18.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_axial_ratio_cost",
    },
)

SIMULATION_OBJECTIVE_NAMES = tuple(str(definition["name"]) for definition in COST_DEFINITIONS)
_PIN_STATE_RE = re.compile(r"pinState(\d+)", re.IGNORECASE)


def _extract_value_for_cost(loaded_items: Sequence[RawDataView]) -> dict[str, object]:
    s11_by_state = _items_by_pin_state(loaded_items, "s11")
    gain_by_state = _items_by_pin_state(loaded_items, "gain_lhcp")
    axial_ratio_by_state = _items_by_pin_state(loaded_items, "axial_ratio")
    gain_curves = {state: _gain_curve(gain_by_state[state]) for state in PIN_STATES}
    peak_gain, peak_theta = _peak_gain_curve(gain_curves)
    return {
        "s11_by_state": tuple(
            _curve_along_axis(s11_by_state[state], "Freq", frequency_to_ghz)
            for state in PIN_STATES
        ),
        "gain_envelope": _gain_envelope(gain_curves),
        "peak_gain": peak_gain,
        "back_lobe_gain": _back_lobe_curve(gain_curves),
        "axial_ratio_by_state": tuple(
            _axial_ratio_curve(axial_ratio_by_state[state], peak_theta[state])
            for state in PIN_STATES
        ),
    }


def _items_by_pin_state(items: Sequence[RawDataView], prefix: str) -> dict[int, RawDataView]:
    by_state: dict[int, RawDataView] = {}
    for item in items:
        if item.name.startswith(prefix):
            state = _pin_state(item)
            if state in PIN_STATES:
                by_state[state] = item
    missing = tuple(state for state in PIN_STATES if state not in by_state)
    if missing:
        raise ValueError(f"missing {prefix} rawData for pin states: {missing}")
    return by_state


def _gain_curve(item: RawDataView) -> tuple[np.ndarray, np.ndarray]:
    item = _select_phi(item)
    if item.has_axis("Freq"):
        item = item.select("Freq", TARGET_FREQ_GHZ, FREQ_TOL_GHZ, converter=frequency_to_ghz)
    return _curve_along_axis(item, "Theta", angle_to_degrees)


def _gain_envelope(curves: Mapping[int, tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    reference_theta, _reference_gain = curves[PIN_STATES[0]]
    aligned_gains = []
    for state in PIN_STATES:
        theta, gain = curves[state]
        if theta.shape != reference_theta.shape or not np.allclose(
            theta, reference_theta, atol=ANGLE_TOL_DEG, rtol=0.0
        ):
            raise ValueError(f"gain Theta axes are not aligned for pinState={state}")
        aligned_gains.append(gain)
    return reference_theta, np.max(np.vstack(aligned_gains), axis=0)


def _peak_gain_curve(
    curves: Mapping[int, tuple[np.ndarray, np.ndarray]],
) -> tuple[tuple[np.ndarray, np.ndarray], dict[int, float]]:
    peaks: list[float] = []
    peak_theta: dict[int, float] = {}
    for state in PIN_STATES:
        theta, gain = curves[state]
        finite = np.isfinite(theta) & np.isfinite(gain)
        if not np.any(finite):
            raise ValueError(f"pinState={state} has no finite gain values")
        index = int(np.argmax(np.where(finite, gain, -np.inf)))
        peaks.append(float(gain[index]))
        peak_theta[state] = float(theta[index])
    return (np.asarray(PIN_STATES, dtype=float), np.asarray(peaks, dtype=float)), peak_theta


def _back_lobe_curve(curves: Mapping[int, tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    values: list[float] = []
    for state in PIN_STATES:
        theta, gain = curves[state]
        mask = np.isfinite(theta) & np.isfinite(gain) & (
            ((theta >= -180.0) & (theta <= -150.0))
            | ((theta >= 150.0) & (theta <= 180.0))
        )
        if not np.any(mask):
            raise ValueError(f"pinState={state} has no finite back-lobe gain values")
        values.append(float(np.max(gain[mask])))
    return np.asarray(PIN_STATES, dtype=float), np.asarray(values, dtype=float)


def _axial_ratio_curve(item: RawDataView, peak_theta: float) -> tuple[np.ndarray, np.ndarray]:
    item = _select_phi(item)
    item = item.select("Theta", peak_theta, ANGLE_TOL_DEG, period=360.0, converter=angle_to_degrees)
    return _curve_along_axis(item, "Freq", frequency_to_ghz)


def _select_phi(item: RawDataView) -> RawDataView:
    if not item.has_axis("Phi"):
        return item
    return item.select("Phi", TARGET_PHI_DEG, ANGLE_TOL_DEG, period=360.0, converter=angle_to_degrees)


def _curve_along_axis(item: RawDataView, axis_name: str, converter) -> tuple[np.ndarray, np.ndarray]:
    if not item.has_axis(axis_name):
        raise ValueError(f"{item.name} missing {axis_name} axis")
    x_values = item.axis_coordinates(axis_name, converter)
    data = np.asarray(item.data)
    data = (np.real(data) if np.iscomplexobj(data) else data).astype(float)
    axis = item.axis_index(axis_name)
    matrix = np.moveaxis(data, axis, 0).reshape(x_values.size, -1)
    y_values = np.asarray([_finite_mean(row) for row in matrix], dtype=float)
    finite = np.isfinite(x_values) & np.isfinite(y_values)
    if not np.any(finite):
        raise ValueError(f"{item.name} has no finite {axis_name} curve values")
    return x_values[finite], y_values[finite]


def _finite_mean(values: object) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(finite.mean()) if finite.size else float("nan")


def _pin_state(item: RawDataView) -> int | None:
    raw = item.metadata.get("pin_state")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        match = _PIN_STATE_RE.search(item.name)
        return int(match.group(1)) if match else None


def calculate_s11_band_cost(value_for_cost: object, definition: Mapping[str, object], **curve) -> float:
    """Evaluate every state and use the least compliant state as the objective."""

    state_costs = tuple(
        calculate_2d_curve_cost(state_curve, definition, **curve)
        for state_curve in value_for_cost
    )
    return float(max(state_costs))


def calculate_axial_ratio_cost(value_for_cost: object, definition: Mapping[str, object], **curve) -> float:
    """Evaluate axial ratio at all three peak-gain directions without summing states."""

    state_costs = tuple(
        calculate_2d_curve_cost(state_curve, definition, **curve)
        for state_curve in value_for_cost
    )
    return float(max(state_costs))


def rawdata_importance_weights(
    sample_rawdata: Sequence[RawDataItem],
    *,
    floor: float = 0.25,
    boost: float = 2.0,
) -> tuple[dict[str, np.ndarray], ...]:
    """Emphasize objective-relevant regions during full-field surrogate training."""

    base = max(0.0, float(floor))
    important = base + max(0.0, float(boost))
    out: list[dict[str, np.ndarray]] = []
    for item in sample_rawdata:
        loaded = RawDataView.from_item(item)
        weights = np.full(np.asarray(loaded.data).shape, base, dtype=np.float32)
        if loaded.name.startswith("s11") or loaded.name.startswith("axial_ratio"):
            weights[...] = important
        elif loaded.name.startswith("gain_lhcp"):
            mark_axis_range(
                weights,
                loaded,
                "Theta",
                *GAIN_COVERAGE_RANGE_DEG,
                important,
                converter=angle_to_degrees,
            )
            for low, high in BACK_LOBE_RANGES_DEG:
                mark_axis_range(weights, loaded, "Theta", low, high, important, converter=angle_to_degrees)
        out.append({loaded.data_key: weights})
    return tuple(out)


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
    """Calculate independent objectives from one current or archived rawData sample."""

    loaded_items = load_rawdata_views(sample_rawdata)
    try:
        costs = calculate_defined_costs(
            COST_DEFINITIONS,
            _extract_value_for_cost(loaded_items),
            globals(),
            **COST_CURVE,
        )
    except COST_CALCULATION_ERRORS:
        return error_costs(get_objective_count(), error_cost=ERROR_COST)
    if not constraint_expressions(parameter_config):
        return costs
    try:
        return costs + (constraint_cost(raw_variables, parameter_config, **CONSTRAINT_COST_CURVE),)
    except CONSTRAINT_CALCULATION_ERRORS:
        return costs + (ERROR_COST,)


def get_objective_names() -> tuple[str, ...]:
    return SIMULATION_OBJECTIVE_NAMES + (
        ("cost_constraints",) if constraint_expressions(parameter_config) else ()
    )


def get_objective_count() -> int:
    return len(get_objective_names())
