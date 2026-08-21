"""Dynamic rawData-to-cost calculation for the Newchoke HFSS task."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import numpy as np

from . import parameters_constraints as parameter_config
from yadof.job_template.cost_misc import (
    ALL,
    RawVariables,
    calculate_task_cost,
    objective_names_from_definitions,
)
from yadof.job_template.rawdata_contract import (
    RawDataItem,
    RawDataView,
    angle_to_degrees,
    curve_along_axis,
    frequency_to_ghz,
)


ERROR_COST = 1.0
PIN_STATES = (1, 2, 3)
TARGET_PHI_DEG = 90.0
TARGET_FREQ_GHZ = 2.44
ANGLE_TOL_DEG = 1.5
FREQ_TOL_GHZ = 0.02
GAIN_COVERAGE_RANGE_DEG = (-60.0, 60.0)

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
        "calculator": "calculate_worst_curve_cost",
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
        "calculator": "calculate_worst_curve_cost",
    },
)

_PIN_STATE_RE = re.compile(r"pinState(\d+)", re.IGNORECASE)


def _extract_value_for_cost(loaded_items: Sequence[RawDataView]) -> dict[str, object]:
    s11_by_state = _items_by_pin_state(loaded_items, "s11")
    gain_by_state = _items_by_pin_state(loaded_items, "gain_lhcp")
    axial_ratio_by_state = _items_by_pin_state(loaded_items, "axial_ratio")
    gain_curves = {state: _gain_curve(gain_by_state[state]) for state in PIN_STATES}
    peak_gain, peak_theta = _peak_gain_curve(gain_curves)
    return {
        "s11_by_state": tuple(
            curve_along_axis(s11_by_state[state], "Freq", frequency_to_ghz)
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
    return curve_along_axis(item, "Theta", angle_to_degrees)


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
    return curve_along_axis(item, "Freq", frequency_to_ghz)


def _select_phi(item: RawDataView) -> RawDataView:
    if not item.has_axis("Phi"):
        return item
    return item.select("Phi", TARGET_PHI_DEG, ANGLE_TOL_DEG, period=360.0, converter=angle_to_degrees)


def _pin_state(item: RawDataView) -> int | None:
    raw = item.metadata.get("pin_state")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        match = _PIN_STATE_RE.search(item.name)
        return int(match.group(1)) if match else None


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
    """Calculate independent objectives from one current or archived rawData sample."""

    return calculate_task_cost(
        sample_rawdata,
        raw_variables,
        definitions=COST_DEFINITIONS,
        extract_value_for_cost=_extract_value_for_cost,
        parameter_config=parameter_config,
        cost_curve=COST_CURVE,
        constraint_curve=CONSTRAINT_COST_CURVE,
    )


def get_objective_names() -> tuple[str, ...]:
    return objective_names_from_definitions(
        COST_DEFINITIONS,
        parameter_config,
    )
