from __future__ import annotations

import json

import numpy as np
import pytest

from yadof.job_template.cost_misc import (
    FIRST,
    LAST,
    calculate_2d_curve_cost,
    calculate_rawdata_cost,
    calculate_registered_cost,
    calculate_task_cost,
    calculate_worst_curve_cost,
    objective_names_from_definitions,
    soft_cost,
    strict_finite_mean,
)
from yadof.job_template.rawdata_contract import RawDataContractError


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


def test_worst_curve_cost_uses_largest_member_cost():
    definition = {
        "goal": 0.0,
        "worst": 10.0,
        "ext_ratio": 0.0,
        "data_range": (FIRST, 1),
    }

    cost = calculate_worst_curve_cost(
        (
            ([0.0], [2.0]),
            ([0.0], [8.0]),
        ),
        definition,
        **COST_CURVE,
    )

    assert cost == pytest.approx(
        soft_cost(8.0, goal=0.0, worst=10.0, **COST_CURVE)
    )


def test_defined_task_cost_helper_owns_dispatch_and_error_fallback():
    definitions = (
        {
            "name": "response_cost",
            "value_for_cost": "response",
            "goal": 0.0,
            "worst": 10.0,
        },
    )
    sample = (
        {
            "values": np.asarray(5.0),
            "metadata": json.dumps(
                {
                    "schema_version": 1,
                    "rawdata_name": "response",
                    "shape": [],
                }
            ),
        },
    )

    cost = calculate_task_cost(
        sample,
        None,
        definitions=definitions,
        extract_value_for_cost=lambda items: {
            "response": float(items[0].data),
        },
        cost_curve=COST_CURVE,
    )
    error = calculate_task_cost(
        (),
        None,
        definitions=definitions,
        extract_value_for_cost=lambda _items: (_ for _ in ()).throw(
            ValueError("missing response")
        ),
        cost_curve={**COST_CURVE, "error_cost": 1.1},
    )

    assert cost == pytest.approx((0.5,))
    assert error == (1.1,)
    assert objective_names_from_definitions(definitions) == ("response_cost",)


def test_rawdata_cost_callback_owns_width_and_failure_fallback():
    sample = (
        {
            "values": np.asarray(5.0),
            "metadata": json.dumps(
                {
                    "schema_version": 1,
                    "rawdata_name": "response",
                    "shape": [],
                }
            ),
        },
    )

    valid = calculate_rawdata_cost(
        sample,
        None,
        objective_names=("response",),
        calculate_loaded_cost=lambda items, _variables: (
            strict_finite_mean(items[0].data),
        ),
    )
    wrong_width = calculate_rawdata_cost(
        sample,
        None,
        objective_names=("first", "second"),
        calculate_loaded_cost=lambda _items, _variables: (1.0,),
        error_cost=1.1,
    )

    assert valid == (5.0,)
    assert wrong_width == (1.1, 1.1)
    assert strict_finite_mean([1.0, np.nan], error_cost=9.0) == 9.0


def test_rawdata_cost_callback_does_not_hide_contract_errors():
    malformed = (
        {
            "values": np.asarray(5.0),
            "metadata": json.dumps(
                {
                    "rawdata_name": "response",
                    "shape": [],
                }
            ),
        },
    )

    with pytest.raises(RawDataContractError, match="schema_version"):
        calculate_rawdata_cost(
            malformed,
            None,
            objective_names=("response",),
            calculate_loaded_cost=lambda items, _variables: (
                float(items[0].data),
            ),
        )

    with pytest.raises(RawDataContractError, match="schema_version"):
        calculate_task_cost(
            malformed,
            None,
            definitions=(
                {
                    "name": "response",
                    "value_for_cost": "response",
                    "goal": 0.0,
                    "worst": 10.0,
                },
            ),
            extract_value_for_cost=lambda items: {
                "response": float(items[0].data),
            },
            cost_curve=COST_CURVE,
        )
