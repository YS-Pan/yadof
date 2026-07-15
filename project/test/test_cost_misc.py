from __future__ import annotations

import pytest

from project.job_template.cost_misc import (
    FIRST,
    LAST,
    calculate_2d_curve_cost,
    calculate_registered_cost,
    soft_cost,
)


COST_CURVE = {"error_cost": 1.0, "edge_cost": 0.1, "tanh_slope": None}


def test_registered_simple_cost_uses_definition_goal_and_worst():
    definition = {
        "value_for_cost": "value",
        "goal": -12.0,
        "worst": -3.0,
        "calculator": None,
    }

    cost = calculate_registered_cost(definition, {"value": -7.5}, {}, **COST_CURVE)

    assert cost == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("definition", "curve", "expected_value"),
    (
        (
            {"goal": -12.0, "worst": -3.0, "ext_ratio": 0.5, "data_range": (2.4, 2.5)},
            ([2.3, 2.4, 2.5, 2.6], [-30.0, -12.0, -6.0, 0.0]),
            -7.5,
        ),
        (
            {"goal": 8.0, "worst": 3.0, "ext_ratio": 0.5, "data_range": (LAST, 2)},
            ([0.0, 1.0, 2.0], [10.0, 7.0, 3.0]),
            4.0,
        ),
        (
            {"goal": 0.0, "worst": 10.0, "ext_ratio": 0.0, "data_range": (FIRST, 2)},
            ([0.0, 1.0, 2.0], [2.0, 4.0, 10.0]),
            3.0,
        ),
        (
            {"goal": 0.0, "worst": 10.0, "ext_ratio": 0.0, "data_range": (1.0, 3.0)},
            ([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0, 9.0, 10.0]),
            4.0,
        ),
        (
            {"goal": 0.0, "worst": 10.0, "ext_ratio": 0.0, "data_range": (1.0, 3.5)},
            ([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 9.0, 2.0, 4.0, 10.0]),
            3.0,
        ),
    ),
)
def test_2d_curve_cost_selection_modes(definition, curve, expected_value):
    cost = calculate_2d_curve_cost(curve, definition)

    assert cost == pytest.approx(
        soft_cost(expected_value, goal=definition["goal"], worst=definition["worst"], **COST_CURVE)
    )


def test_soft_cost_uses_configurable_edge_cost():
    assert soft_cost(-12.0, goal=-12.0, worst=-3.0, **COST_CURVE) == pytest.approx(0.1)
    assert soft_cost(-3.0, goal=-12.0, worst=-3.0, **COST_CURVE) == pytest.approx(0.9)
    assert soft_cost(-7.5, goal=-12.0, worst=-3.0, **COST_CURVE) == pytest.approx(0.5)
