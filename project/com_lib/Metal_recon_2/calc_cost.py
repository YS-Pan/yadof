"""Dynamic rawData-to-cost calculation for the Metal_recon_ant HFSS task."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import numpy as np

from . import parameters_constraints as parameter_config
from .cost_misc import (ALL, CONSTRAINT_CALCULATION_ERRORS, COST_CALCULATION_ERRORS, FIRST, LAST, RawVariables, calculate_2d_curve_cost, calculate_defined_costs, constraint_cost, constraint_expressions, error_costs, mean_cost, soft_cost,)
from .rawdata_contract import (RawDataItem, RawDataView, angle_to_degrees, combine_2d_curves, frequency_to_ghz, load_rawdata_views, mark_axis_points,mark_axis_range,)

ERROR_COST = 1.1

PIN_STATES = (1, 2, 3, 4)
S11_BAND_GHZ = (2.40, 2.48)
TARGET_FREQ_GHZ = 2.44
TARGET_PHI_DEG = 90.0
TARGET_THETA_DEG = (-30, 0, 30)
ANGLE_TOL_DEG = 1.5
FREQ_TOL_GHZ = 0.02

COST_CURVE = {"error_cost": ERROR_COST, "edge_cost": 0.1, "tanh_slope": None}
CONSTRAINT_COST_CURVE = dict(COST_CURVE)

# calculator:
#   None                 -> apply tanh cost using this dictionary's goal and worst
#   "_cost_function"     -> call the named function with (value_for_cost, definition)
COST_DEFINITIONS = (
    {
        "name": "cost_s11_band",
        "value_for_cost": "s11_band",
        "goal": -12.0,
        "worst": -3.0,
        "ext_ratio": 0.2,
        "data_range": S11_BAND_GHZ,
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "cost_gain_steering",
        "value_for_cost": "gain",
        "calculator": "_cost_gain_steering",
    },
    {
        "name": "cost_gain_split",
        "value_for_cost": "gain",
        "calculator": "_cost_gain_split",
    },
    {
        "name": "cost_gain_broadside",
        "value_for_cost": "gain_broadside",
        "goal": 8.0,
        "worst": 3.0,
        "calculator": None,
    },
)

SIMULATION_OBJECTIVE_NAMES = tuple(str(definition["name"]) for definition in COST_DEFINITIONS)
_PIN_STATE_RE = re.compile(r"pinState(\d+)", re.IGNORECASE)

#--------------------------------------User Defined Cost Calculation Process--------------------------------------------

def _extract_value_for_cost(
    loaded_items: Sequence[RawDataView],
) -> dict[str, object]:
    s11_items = tuple(item for item in loaded_items if item.name.startswith("s11"))
    gain_by_state = {
        state: item
        for item in loaded_items
        if item.name.startswith("gain") and (state := _pin_state(item)) is not None
    }
    if not s11_items or any(state not in gain_by_state for state in PIN_STATES):
        raise ValueError("S11 or pin-state gain rawData is incomplete")

    gain = {state: _gain_cut(gain_by_state[state]) for state in PIN_STATES}
    return {
        "s11_band": combine_2d_curves(s11_items, "Freq", frequency_to_ghz),
        "gain": gain,
        "gain_broadside": gain[4][0],
    }


#--------------------------------------User Defined Data-processing functions--------------------------------------------

def _gain_cut(item: RawDataView) -> dict[int, float]:
    if item.has_axis("Freq"):
        item = item.select("Freq", TARGET_FREQ_GHZ, FREQ_TOL_GHZ, converter=frequency_to_ghz)
    if item.has_axis("Phi"):
        item = item.select(
            "Phi",
            TARGET_PHI_DEG,
            ANGLE_TOL_DEG,
            period=360.0,
            converter=angle_to_degrees,
        )
    if not item.has_axis("Theta"):
        values = np.asarray(item.data, dtype=float).ravel()
        if values.size == len(TARGET_THETA_DEG):
            return {int(angle): float(value) for angle, value in zip(TARGET_THETA_DEG, values)}
        raise KeyError("Theta")

    return {
        int(angle): float(
            np.asarray(
                item.select(
                    "Theta",
                    angle,
                    ANGLE_TOL_DEG,
                    period=360.0,
                    converter=angle_to_degrees,
                ).data
            ).squeeze()
        )
        for angle in TARGET_THETA_DEG
    }


def _cost_gain_steering(
    value_for_cost: object,
    definition: Mapping[str, object] | None = None,
    **curve,
) -> float:
    gain = value_for_cost  # type: ignore[assignment]
    g1, g2 = gain[1], gain[2]
    c1 = mean_cost(
        (
            soft_cost(g1[-30], goal=7.0, worst=2.0, **curve),
            soft_cost(g1[30], goal=0.0, worst=5.0, **curve),
            soft_cost(g1[-30] - g1[30], goal=3.0, worst=0.0, **curve),
        ),
        error_cost=ERROR_COST,
    )
    c2 = mean_cost(
        (
            soft_cost(g2[-30], goal=0.0, worst=5.0, **curve),
            soft_cost(g2[30], goal=7.0, worst=2.0, **curve),
            soft_cost(g2[30] - g2[-30], goal=3.0, worst=0.0, **curve),
        ),
        error_cost=ERROR_COST,
    )
    return 0.5 * (c1 + c2)


def _cost_gain_split(
    value_for_cost: object,
    definition: Mapping[str, object] | None = None,
    **curve,
) -> float:
    gain = value_for_cost  # type: ignore[assignment]
    g = gain[3]
    return mean_cost(
        (
            soft_cost(g[-30], goal=7.0, worst=2.0, **curve),
            soft_cost(g[0], goal=-15.0, worst=-8.0, **curve),
            soft_cost(g[30], goal=7.0, worst=2.0, **curve),
            soft_cost(
                min(g[-30], g[30]) - g[0],
                goal=15.0,
                worst=5.0,
                **curve,
            ),
        ),
        error_cost=ERROR_COST,
    )

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
            mark_axis_range(
                weights,
                loaded,
                "Freq",
                S11_BAND_GHZ[0],
                S11_BAND_GHZ[1],
                important,
                converter=frequency_to_ghz,
            )
        elif loaded.name.startswith("gain"):
            mark_axis_points(
                weights,
                loaded,
                "Theta",
                TARGET_THETA_DEG,
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


def _pin_state(item: RawDataView) -> int | None:
    raw = item.metadata.get("pin_state")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        match = _PIN_STATE_RE.search(item.name)
        return int(match.group(1)) if match else None

