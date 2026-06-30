from __future__ import annotations

import pytest

from project.job_template import calc_cost
from project.job_template.calc_cost import (
    calculate_2d_curve_cost,
    calculate_cost,
    rawdata_importance_weights,
)
from project.job_template.cost_misc import FIRST, LAST, calculate_registered_cost, soft_cost
from project.job_template.rawdata_contract import RAWDATA_SCHEMA_VERSION


def _metadata(rawdata_name: str, shape, axes, *, expression: str):
    return {
        "schema_version": RAWDATA_SCHEMA_VERSION,
        "rawdata_name": rawdata_name,
        "expression": expression,
        "source": "test",
        "shape": list(shape),
        "axis_names": [axis["name"] for axis in axes],
        "axes": list(axes),
    }


def _modal_item(expression: str, values):
    axes = [{"index": 0, "size": 5, "name": "Freq", "values_key": "axis_Freq", "unit": "GHz"}]
    return {
        "axis_Freq": [1.0, 2.0, 3.0, 4.0, 5.0],
        "unit_Freq": "GHz",
        "data": list(values),
        "metadata": _metadata(expression, [5], axes, expression=expression),
    }


def _good_sample():
    values_by_expression = {
        "dB(mag(S(1:3,3:1))+mag(S(1:3,3:2)))": [3.0] * 5,
        "dB(mag(S(3:1,2:3))+mag(S(3:2,2:3)))": [3.0] * 5,
        "dB(S(1:3,2:3))": [-15.0] * 5,
        "dB(mag(S(1:3,4:1))+mag(S(1:3,4:2)))": [-30.0] * 5,
        "dB(mag(S(3:1,4:1))+mag(S(3:1,4:2))+mag(S(3:2,4:1))+mag(S(3:2,4:2)))": [-30.0] * 5,
    }
    return tuple(
        _modal_item(expression, values_by_expression[expression])
        for expression in calc_cost.SIMULATION_OBJECTIVE_NAMES
    )


def test_hfss_costs_use_reference_objectives():
    raw_variables = {parameter.name: 1.0 for parameter in calc_cost.parameter_config.get_parameters()}
    costs = calculate_cost(_good_sample(), raw_variables)

    assert len(costs) == calc_cost.get_objective_count()
    assert all(0.0 <= value <= 1.0 for value in costs)
    assert all(value <= 0.1 for value in costs)


def test_cost_definitions_register_simple_and_complex_calculators():
    definitions = {definition["name"]: definition for definition in calc_cost.COST_DEFINITIONS}

    assert tuple(definitions) == calc_cost.SIMULATION_OBJECTIVE_NAMES
    assert all(definition["value_for_cost"] == definition["name"] for definition in definitions.values())
    assert all(definition["calculator"] == "calculate_2d_curve_cost" for definition in definitions.values())
    assert all(definition["ext_ratio"] == 0.7 for definition in definitions.values())
    assert all(definition["data_range"] == (calc_cost.ALL, 0) for definition in definitions.values())
    assert definitions["dB(S(1:3,2:3))"]["goal"] == -15.0
    assert definitions["dB(S(1:3,2:3))"]["worst"] == 0.0


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
    assert len(violated) == 6
    assert violated[-1] == pytest.approx(0.5)
    assert satisfied[-1] == pytest.approx(0.1)


def test_invalid_constraint_only_fails_constraint_objective(monkeypatch):
    monkeypatch.setattr(calc_cost.parameter_config, "CONSTRAINTS", ("missing_name - 1",))

    costs = calculate_cost(_good_sample(), {calc_cost.parameter_config.get_parameters()[0].name: 2.0})

    assert all(value <= 0.1 for value in costs[:5])
    assert costs[-1] == calc_cost.ERROR_COST


def test_rawdata_importance_weights_emphasize_modal_curves():
    weights = rawdata_importance_weights(_good_sample(), floor=0.25, boost=2.0)

    assert len(weights) == 5
    assert all(float(weight["data"].min()) == pytest.approx(2.25) for weight in weights)
    assert all(float(weight["data"].max()) == pytest.approx(2.25) for weight in weights)
