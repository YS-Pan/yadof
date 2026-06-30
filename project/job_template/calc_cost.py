"""Modal rawData-to-cost calculation for the HFSS task."""

from __future__ import annotations

from collections.abc import Sequence

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
from .rawdata_contract import RawDataItem, RawDataView, load_rawdata_views

ERROR_COST = 1.1
COST_CURVE = {"error_cost": ERROR_COST, "edge_cost": 0.1, "tanh_slope": None}
CONSTRAINT_COST_CURVE = dict(COST_CURVE)

COST_DEFINITIONS = (
    {
        "name": "dB(mag(S(1:3,3:1))+mag(S(1:3,3:2)))",
        "value_for_cost": "dB(mag(S(1:3,3:1))+mag(S(1:3,3:2)))",
        "goal": 3.0,
        "worst": -12.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "dB(mag(S(3:1,2:3))+mag(S(3:2,2:3)))",
        "value_for_cost": "dB(mag(S(3:1,2:3))+mag(S(3:2,2:3)))",
        "goal": 3.0,
        "worst": -12.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "dB(S(1:3,2:3))",
        "value_for_cost": "dB(S(1:3,2:3))",
        "goal": -15.0,
        "worst": 0.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "dB(mag(S(1:3,4:1))+mag(S(1:3,4:2)))",
        "value_for_cost": "dB(mag(S(1:3,4:1))+mag(S(1:3,4:2)))",
        "goal": -30.0,
        "worst": -5.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
    {
        "name": "dB(mag(S(3:1,4:1))+mag(S(3:1,4:2))+mag(S(3:2,4:1))+mag(S(3:2,4:2)))",
        "value_for_cost": "dB(mag(S(3:1,4:1))+mag(S(3:1,4:2))+mag(S(3:2,4:1))+mag(S(3:2,4:2)))",
        "goal": -30.0,
        "worst": 0.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
)

SIMULATION_OBJECTIVE_NAMES = tuple(str(definition["name"]) for definition in COST_DEFINITIONS)


#--------------------------------------User Defined Cost Calculation Process--------------------------------------------

def _extract_value_for_cost(
    loaded_items: Sequence[RawDataView],
) -> dict[str, object]:
    value_for_cost: dict[str, object] = {}
    for item in loaded_items:
        expression = str(item.metadata.get("expression") or item.name)
        if expression in SIMULATION_OBJECTIVE_NAMES:
            value_for_cost[expression] = (item.axis_coordinates("Freq"), item.data)
    missing = tuple(name for name in SIMULATION_OBJECTIVE_NAMES if name not in value_for_cost)
    if missing:
        raise ValueError(f"missing modal rawData: {missing}")
    return value_for_cost


#--------------------------------------Surrogate functions--------------------------------------------

def rawdata_importance_weights(
    sample_rawdata: Sequence[RawDataItem],
    *,
    floor: float = 0.25,
    boost: float = 2.0,
) -> tuple[dict[str, np.ndarray], ...]:
    base = max(0.0, float(floor))
    important = max(base, base + max(0.0, float(boost)))
    out: list[dict[str, np.ndarray]] = []
    for item in sample_rawdata:
        loaded = RawDataView.from_item(item)
        values = np.asarray(loaded.data, dtype=float)
        out.append({loaded.data_key: np.full(values.shape, important, dtype=np.float32)} if values.size else {})
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
