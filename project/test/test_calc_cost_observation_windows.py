from __future__ import annotations

import numpy as np
import pytest

from project.job_template import calc_cost
from project.job_template.calc_cost import (
    calculate_2d_curve_cost,
    calculate_cost,
    rawdata_importance_weights,
)
from project.job_template.cost_misc import FIRST, LAST, calculate_registered_cost, soft_cost
from project.job_template.rawdata_contract import RAWDATA_SCHEMA_VERSION


FREQ_VALUES = np.asarray([2.40, 2.42, 2.44, 2.46, 2.48], dtype=float)
GAIN_FREQ_VALUES = np.asarray([2.44], dtype=float)
GAIN_THETA_VALUES = np.asarray([-30.0, 0.0, 30.0], dtype=float)
AXIAL_THETA_VALUES = np.asarray([-14.0, 0.0, 14.0], dtype=float)
PHI_VALUES = np.asarray([0.0, 90.0, 180.0], dtype=float)


def _item(rawdata_name: str, data, axes, *, expression: str, pin_state: int | None = None):
    shape = tuple(int(size) for size in np.asarray(data).shape)
    axis_descriptors = [
        {
            "index": index,
            "size": int(len(values)),
            "name": name,
            "values_key": f"axis_{name}",
            "unit": unit,
        }
        for index, (name, values, unit) in enumerate(axes)
    ]
    metadata = {
        "schema_version": RAWDATA_SCHEMA_VERSION,
        "rawdata_name": rawdata_name,
        "expression": expression,
        "source": "test",
        "shape": list(shape),
        "axis_names": [name for name, _values, _unit in axes],
        "axes": axis_descriptors,
    }
    if pin_state is not None:
        metadata["pin_state"] = int(pin_state)

    payload = {
        "data": np.asarray(data, dtype=float),
        "metadata": metadata,
    }
    for name, values, unit in axes:
        payload[f"axis_{name}"] = np.asarray(values, dtype=float)
        payload[f"unit_{name}"] = unit
    return payload


def _s11_item(state: int):
    return _item(
        f"s11_pinState{state}",
        np.full(FREQ_VALUES.shape, -15.0, dtype=float),
        (("Freq", FREQ_VALUES, "GHz"),),
        expression=calc_cost.S11_EXPR if hasattr(calc_cost, "S11_EXPR") else "dB(S(1,1))",
        pin_state=state,
    )


def _gain_item(state: int):
    data = np.full((GAIN_FREQ_VALUES.size, GAIN_THETA_VALUES.size, PHI_VALUES.size), -2.0, dtype=float)
    theta_index = int(np.flatnonzero(GAIN_THETA_VALUES == calc_cost.GAIN_TARGET_THETA_BY_STATE[state])[0])
    phi_index = int(np.flatnonzero(PHI_VALUES == calc_cost.TARGET_PHI_DEG)[0])
    data[:, theta_index, phi_index] = 8.0
    return _item(
        f"gain_lhcp_pinState{state}",
        data,
        (
            ("Freq", GAIN_FREQ_VALUES, "GHz"),
            ("Theta", GAIN_THETA_VALUES, "deg"),
            ("Phi", PHI_VALUES, "deg"),
        ),
        expression="dB(RealizedGainLHCP)",
        pin_state=state,
    )


def _axial_ratio_item(state: int):
    cut_values = np.asarray([0.0, 1.0], dtype=float)
    data = np.full(
        (FREQ_VALUES.size, AXIAL_THETA_VALUES.size, PHI_VALUES.size, cut_values.size),
        20.0,
        dtype=float,
    )
    theta_index = int(np.flatnonzero(AXIAL_THETA_VALUES == calc_cost.AXIAL_RATIO_TARGET_THETA_BY_STATE[state])[0])
    phi_index = int(np.flatnonzero(PHI_VALUES == calc_cost.TARGET_PHI_DEG)[0])
    data[:, theta_index, phi_index, :] = 0.0
    return _item(
        f"axial_ratio_pinState{state}",
        data,
        (
            ("Freq", FREQ_VALUES, "GHz"),
            ("Theta", AXIAL_THETA_VALUES, "deg"),
            ("Phi", PHI_VALUES, "deg"),
            ("Cut", cut_values, ""),
        ),
        expression="dB(AxialRatioValue)",
        pin_state=state,
    )


def _good_sample():
    return tuple(
        item
        for state in calc_cost.PIN_STATES
        for item in (_s11_item(state), _gain_item(state), _axial_ratio_item(state))
    )


def test_hfss_costs_use_current_newchoke_objectives():
    raw_variables = {parameter.name: 1.0 for parameter in calc_cost.parameter_config.get_parameters()}
    costs = calculate_cost(_good_sample(), raw_variables)

    assert len(costs) == calc_cost.get_objective_count()
    assert all(0.0 <= value <= 1.0 for value in costs)
    assert all(value <= 0.15 for value in costs)


def test_full_matrix_far_field_rawdata_does_not_return_error_cost():
    costs = calculate_cost(_good_sample(), None)

    assert costs == pytest.approx((costs[0], costs[1], costs[2]))
    assert all(value != calc_cost.ERROR_COST for value in costs)
    assert costs[1] <= 0.15
    assert costs[2] <= 0.15


def test_cost_definitions_register_current_objective_calculators():
    definitions = {definition["name"]: definition for definition in calc_cost.COST_DEFINITIONS}

    assert tuple(definitions) == calc_cost.SIMULATION_OBJECTIVE_NAMES
    assert definitions["cost_s11_band"]["value_for_cost"] == "s11_band"
    assert definitions["cost_gain_lhcp_targets"]["value_for_cost"] == "gain_lhcp_targets"
    assert definitions["cost_axial_ratio_targets"]["value_for_cost"] == "axial_ratio_targets"
    assert all(definition["calculator"] == "calculate_2d_curve_cost" for definition in definitions.values())
    assert all(definition["data_range"] == (calc_cost.ALL, 0) for definition in definitions.values())
    assert definitions["cost_s11_band"]["goal"] == -12.0
    assert definitions["cost_gain_lhcp_targets"]["goal"] == 7.0
    assert definitions["cost_axial_ratio_targets"]["worst"] == 18.0


def test_registered_simple_cost_uses_definition_goal_and_worst():
    definition = {
        "value_for_cost": "value",
        "goal": -12.0,
        "worst": -3.0,
        "calculator": None,
    }

    cost = calculate_registered_cost(definition, {"value": -7.5}, {}, **calc_cost.COST_CURVE)

    assert cost == pytest.approx(0.5)


def test_2d_curve_cost_uses_maximum_when_goal_is_below_worst():
    definition = {
        "goal": -12.0,
        "worst": -3.0,
        "ext_ratio": 0.5,
        "data_range": (2.4, 2.5),
    }

    cost = calculate_2d_curve_cost(
        ([2.3, 2.4, 2.5, 2.6], [-30.0, -12.0, -6.0, 0.0]),
        definition,
    )

    assert cost == pytest.approx(
        soft_cost(-7.5, goal=-12.0, worst=-3.0, **calc_cost.COST_CURVE)
    )


def test_2d_curve_cost_uses_minimum_when_goal_is_above_worst():
    definition = {
        "goal": 8.0,
        "worst": 3.0,
        "ext_ratio": 0.5,
        "data_range": (LAST, 2),
    }

    cost = calculate_2d_curve_cost(
        ([0.0, 1.0, 2.0], [10.0, 7.0, 3.0]),
        definition,
    )

    assert cost == pytest.approx(
        soft_cost(4.0, goal=8.0, worst=3.0, **calc_cost.COST_CURVE)
    )


def test_2d_curve_cost_can_use_first_values():
    definition = {
        "goal": 0.0,
        "worst": 10.0,
        "ext_ratio": 0.0,
        "data_range": (FIRST, 2),
    }

    cost = calculate_2d_curve_cost(
        ([0.0, 1.0, 2.0], [2.0, 4.0, 10.0]),
        definition,
    )

    assert cost == pytest.approx(
        soft_cost(3.0, goal=0.0, worst=10.0, **calc_cost.COST_CURVE)
    )


def test_2d_curve_cost_numeric_range_is_closed_when_both_endpoints_exist():
    definition = {
        "goal": 0.0,
        "worst": 10.0,
        "ext_ratio": 0.0,
        "data_range": (1.0, 3.0),
    }

    cost = calculate_2d_curve_cost(
        ([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0, 9.0, 10.0]),
        definition,
    )

    assert cost == pytest.approx(
        soft_cost(4.0, goal=0.0, worst=10.0, **calc_cost.COST_CURVE)
    )


def test_2d_curve_cost_numeric_range_is_open_when_an_endpoint_is_missing():
    definition = {
        "goal": 0.0,
        "worst": 10.0,
        "ext_ratio": 0.0,
        "data_range": (1.0, 3.5),
    }

    cost = calculate_2d_curve_cost(
        ([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 9.0, 2.0, 4.0, 10.0]),
        definition,
    )

    assert cost == pytest.approx(
        soft_cost(3.0, goal=0.0, worst=10.0, **calc_cost.COST_CURVE)
    )


def test_soft_cost_uses_configurable_edge_cost():
    assert soft_cost(-12.0, goal=-12.0, worst=-3.0, **calc_cost.COST_CURVE) == pytest.approx(0.1)
    assert soft_cost(-3.0, goal=-12.0, worst=-3.0, **calc_cost.COST_CURVE) == pytest.approx(0.9)
    assert soft_cost(-7.5, goal=-12.0, worst=-3.0, **calc_cost.COST_CURVE) == pytest.approx(0.5)


def test_constraint_cost_uses_raw_variables_and_signed_margins(monkeypatch):
    parameter_name = calc_cost.parameter_config.get_parameters()[0].name
    monkeypatch.setattr(calc_cost.parameter_config, "CONSTRAINTS", (f"${parameter_name} - 1.5",))

    violated = calculate_cost(_good_sample(), {parameter_name: 1.0})
    satisfied = calculate_cost(_good_sample(), {parameter_name: 2.0})

    assert calc_cost.get_objective_names()[-1] == "cost_constraints"
    assert len(violated) == 4
    assert violated[-1] == pytest.approx(0.5)
    assert satisfied[-1] == pytest.approx(0.1)


def test_invalid_constraint_only_fails_constraint_objective(monkeypatch):
    monkeypatch.setattr(calc_cost.parameter_config, "CONSTRAINTS", ("missing_name - 1",))

    costs = calculate_cost(_good_sample(), {calc_cost.parameter_config.get_parameters()[0].name: 2.0})

    assert all(value <= 0.15 for value in costs[:3])
    assert costs[-1] == calc_cost.ERROR_COST


def test_rawdata_importance_weights_emphasize_targets_without_dropping_full_fields():
    weights = rawdata_importance_weights(_good_sample(), floor=0.25, boost=2.0)

    assert len(weights) == len(_good_sample())
    assert all("data" in weight for weight in weights)
    assert all(weight["data"].shape == item["data"].shape for weight, item in zip(weights, _good_sample()))
    assert all(float(weight["data"].min()) >= 0.25 for weight in weights)
    assert all(float(weight["data"].max()) == pytest.approx(2.25) for weight in weights)
    assert any(float(weight["data"].min()) == pytest.approx(0.25) for weight in weights)
