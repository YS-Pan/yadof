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
    combine_2d_curves,
    frequency_to_ghz,
    load_rawdata_views,
    mark_axis_points,
)

ERROR_COST = 1.1

PIN_STATES = (1, 2, 3)
FULL_DATA_RANGE = (ALL, 0)
TARGET_PHI_DEG = 90.0
GAIN_TARGET_FREQ_GHZ = 2.44
GAIN_THETA_RANGE_DEG = (-30.0, 30.0)
GAIN_TARGET_THETA_BY_STATE = {1: -30.0, 2: 30.0, 3: 0.0}
AXIAL_RATIO_TARGET_THETA_BY_STATE = {1: -14.0, 2: 14.0, 3: 0.0}
ANGLE_TOL_DEG = 1.5
FREQ_TOL_GHZ = 0.02

COST_CURVE = {"error_cost": ERROR_COST, "edge_cost": 0.1, "tanh_slope": None}
CONSTRAINT_COST_CURVE = dict(COST_CURVE)

COST_DEFINITIONS = (
    {
        "name": "cost_s11_band",
        "value_for_cost": "s11_band",
        "goal": -12.0,
        "worst": -3.0,
        "ext_ratio": 0.2,
        "data_range": FULL_DATA_RANGE,
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "cost_gain_lhcp_targets",
        "value_for_cost": "gain_lhcp_targets",
        "goal": 7.0,
        "worst": 0.0,
        "ext_ratio": 0.7,
        "data_range": FULL_DATA_RANGE,
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "cost_axial_ratio_targets",
        "value_for_cost": "axial_ratio_targets",
        "goal": 0.0,
        "worst": 18.0,
        "ext_ratio": 0.7,
        "data_range": FULL_DATA_RANGE,
        "calculator": "calculate_2d_curve_cost",
    },
)

SIMULATION_OBJECTIVE_NAMES = tuple(str(definition["name"]) for definition in COST_DEFINITIONS)
_PIN_STATE_RE = re.compile(r"pinState(\d+)", re.IGNORECASE)


#--------------------------------------User Defined Cost Calculation Process--------------------------------------------

def _extract_value_for_cost(
    loaded_items: Sequence[RawDataView],
) -> dict[str, object]:
    s11_by_state = _items_by_pin_state(loaded_items, "s11")
    gain_by_state = _items_by_pin_state(loaded_items, "gain_lhcp")
    axial_ratio_by_state = _items_by_pin_state(loaded_items, "axial_ratio")

    return {
        "s11_band": combine_2d_curves(tuple(s11_by_state[state] for state in PIN_STATES), "Freq", frequency_to_ghz),
        "gain_lhcp_targets": _gain_lhcp_target_curve(gain_by_state),
        "axial_ratio_targets": _axial_ratio_target_curve(axial_ratio_by_state),
    }


#--------------------------------------User Defined Data-processing functions--------------------------------------------

def _items_by_pin_state(
    items: Sequence[RawDataView],
    prefix: str,
) -> dict[int, RawDataView]:
    by_state: dict[int, RawDataView] = {}
    for item in items:
        if not item.name.startswith(prefix):
            continue
        state = _pin_state(item)
        if state in PIN_STATES:
            by_state[int(state)] = item

    missing = tuple(state for state in PIN_STATES if state not in by_state)
    if missing:
        raise ValueError(f"missing {prefix} rawData for pin states: {missing}")
    return by_state


def _gain_lhcp_target_curve(gain_by_state: Mapping[int, RawDataView]) -> tuple[np.ndarray, np.ndarray]:
    x_values: list[float] = []
    y_values: list[float] = []
    for state in PIN_STATES:
        item = _select_phi(gain_by_state[state])
        if item.has_axis("Freq"):
            item = item.select("Freq", GAIN_TARGET_FREQ_GHZ, FREQ_TOL_GHZ, converter=frequency_to_ghz)
        item = _restrict_axis_range(item, "Theta", *GAIN_THETA_RANGE_DEG, converter=angle_to_degrees)
        target_theta = GAIN_TARGET_THETA_BY_STATE[state]
        if item.has_axis("Theta"):
            item = item.select("Theta", target_theta, ANGLE_TOL_DEG, period=360.0, converter=angle_to_degrees)
        x_values.append(float(state))
        y_values.append(_finite_extreme(item.data, largest=True))
    return np.asarray(x_values, dtype=float), np.asarray(y_values, dtype=float)


def _axial_ratio_target_curve(axial_ratio_by_state: Mapping[int, RawDataView]) -> tuple[np.ndarray, np.ndarray]:
    x_values: list[float] = []
    y_values: list[float] = []
    for state in PIN_STATES:
        item = _select_phi(axial_ratio_by_state[state])
        target_theta = AXIAL_RATIO_TARGET_THETA_BY_STATE[state]
        if item.has_axis("Theta"):
            item = item.select("Theta", target_theta, ANGLE_TOL_DEG, period=360.0, converter=angle_to_degrees)
        freq_values, axial_ratio_values = _curve_along_axis(item, "Freq", frequency_to_ghz, largest=True)
        x_values.extend(freq_values.tolist())
        y_values.extend(axial_ratio_values.tolist())
    return np.asarray(x_values, dtype=float), np.asarray(y_values, dtype=float)


def _select_phi(item: RawDataView) -> RawDataView:
    if not item.has_axis("Phi"):
        return item
    return item.select("Phi", TARGET_PHI_DEG, ANGLE_TOL_DEG, period=360.0, converter=angle_to_degrees)


def _restrict_axis_range(
    item: RawDataView,
    axis_name: str,
    low: float,
    high: float,
    *,
    converter=None,
) -> RawDataView:
    if not item.has_axis(axis_name):
        return item
    indices = item.range_indices(axis_name, low, high, converter=converter)
    if indices.size == 0:
        raise ValueError(f"{item.name} has no {axis_name} points in range [{low}, {high}]")

    axis = item.axis_index(axis_name)
    return RawDataView(
        item=item.item,
        metadata=item.metadata,
        data_key=item.data_key,
        data=np.take(item.data, indices, axis=axis),
        axis_names=item.axis_names,
        axis_values={
            key: np.take(values, indices) if key == axis_name else values
            for key, values in item.axis_values.items()
        },
        axis_units=dict(item.axis_units),
    )


def _curve_along_axis(
    item: RawDataView,
    axis_name: str,
    converter,
    *,
    largest: bool | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if not item.has_axis(axis_name):
        raise ValueError(f"{item.name} missing {axis_name} axis")

    x_values = item.axis_coordinates(axis_name, converter)
    raw_y = np.asarray(item.data)
    data = (np.real(raw_y) if np.iscomplexobj(raw_y) else raw_y).astype(float)
    axis = item.axis_index(axis_name)
    if axis >= data.ndim or x_values.size != data.shape[axis]:
        raise ValueError(
            f"{item.name} {axis_name}/data size mismatch: "
            f"{x_values.size} axis values vs shape {tuple(int(size) for size in data.shape)}"
        )

    matrix = np.moveaxis(data, axis, 0).reshape(x_values.size, -1)
    y_values = np.asarray([_finite_reduce(row, largest=largest) for row in matrix], dtype=float)
    finite = np.isfinite(x_values) & np.isfinite(y_values)
    if not np.any(finite):
        raise ValueError(f"{item.name} has no finite {axis_name} curve values")
    return x_values[finite], y_values[finite]


def _finite_reduce(values: object, *, largest: bool | None = None) -> float:
    data = np.asarray(values, dtype=float)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return float("nan")
    if largest is True:
        return float(finite.max())
    if largest is False:
        return float(finite.min())
    return float(finite.mean())


def _finite_extreme(values: object, *, largest: bool) -> float:
    data = np.asarray(values, dtype=float)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        raise ValueError("no finite values")
    return float(finite.max() if largest else finite.min())


def _pin_state(item: RawDataView) -> int | None:
    raw = item.metadata.get("pin_state")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        match = _PIN_STATE_RE.search(item.name)
        return int(match.group(1)) if match else None


#--------------------------------------Surrogate functions--------------------------------------------

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
        loaded = RawDataView.from_item(item)
        values = np.asarray(loaded.data, dtype=float)
        if values.size == 0:
            out.append({})
            continue

        weights = np.full(values.shape, base, dtype=np.float32)
        if loaded.name.startswith("s11"):
            weights[...] = important
        elif loaded.name.startswith("gain_lhcp"):
            state = _pin_state(loaded)
            targets = (
                (GAIN_TARGET_THETA_BY_STATE[state],)
                if state in GAIN_TARGET_THETA_BY_STATE
                else tuple(GAIN_TARGET_THETA_BY_STATE.values())
            )
            mark_axis_points(
                weights,
                loaded,
                "Theta",
                targets,
                ANGLE_TOL_DEG,
                important,
                period=360.0,
                converter=angle_to_degrees,
            )
        elif loaded.name.startswith("axial_ratio"):
            state = _pin_state(loaded)
            targets = (
                (AXIAL_RATIO_TARGET_THETA_BY_STATE[state],)
                if state in AXIAL_RATIO_TARGET_THETA_BY_STATE
                else tuple(AXIAL_RATIO_TARGET_THETA_BY_STATE.values())
            )
            mark_axis_points(
                weights,
                loaded,
                "Theta",
                targets,
                ANGLE_TOL_DEG,
                important,
                period=360.0,
                converter=angle_to_degrees,
            )
        out.append({loaded.data_key: weights})
    return tuple(out)


#--------------------------------------Fixed functions--------------------------------------------

def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
    """Calculate objective values for one sample from in-memory or file rawData."""

    loaded_items = load_rawdata_views(sample_rawdata)
    try:
        value_for_cost = _extract_value_for_cost(loaded_items)
        costs = calculate_defined_costs(
            COST_DEFINITIONS,
            value_for_cost,
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
