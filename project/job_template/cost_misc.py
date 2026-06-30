"""Reusable cost calculation helpers."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Callable

import numpy as np

RawVariables = Mapping[str, float] | Sequence[float]

ALL = "ALL"
FIRST = "FIRST"
LAST = "LAST"
DEFAULT_DATA_RANGE = (ALL, 0)

COST_CALCULATION_ERRORS = (KeyError, ValueError, IndexError, TypeError, FloatingPointError)
CONSTRAINT_CALCULATION_ERRORS = COST_CALCULATION_ERRORS + (NameError, SyntaxError)

_DOLLAR_VAR_RE = re.compile(r"\$([A-Za-z_]\w*)")


def soft_cost(
    value_for_cost: float,
    goal: float,
    worst: float,
    *,
    error_cost: float = 1.0,
    edge_cost: float = 0.1,
    tanh_slope: float | None = None,
) -> float:
    if value_for_cost is False or value_for_cost is None:
        return float(error_cost)
    value, goal, worst = float(value_for_cost), float(goal), float(worst)
    edge = float(edge_cost)
    slope = 2.0 * math.atanh(1.0 - 2.0 * edge) if tanh_slope is None else float(tanh_slope)
    if (
        not (math.isfinite(value) and math.isfinite(goal) and math.isfinite(worst))
        or goal == worst
        or not (0.0 < edge < 0.5)
        or not (math.isfinite(slope) and slope > 0.0)
    ):
        return float(error_cost)
    position = (value - goal) / (worst - goal)
    return float((math.tanh(slope * (position - 0.5)) + 1.0) / 2.0)


def mean_cost(values: Sequence[float], *, error_cost: float = 1.0) -> float:
    finite = tuple(float(value) for value in values if math.isfinite(float(value)))
    return sum(finite) / len(finite) if finite else float(error_cost)


def calculate_2d_curve_cost(
    value_for_cost: object,
    definition: Mapping[str, object],
    **curve,
) -> float:
    """Calculate one x-y curve's cost using goal/worst direction from a definition."""

    if not isinstance(value_for_cost, (tuple, list)) or len(value_for_cost) != 2:
        raise ValueError("2D value_for_cost must be an (x, y) pair")
    x = np.asarray(value_for_cost[0], dtype=float).ravel()
    raw_y = np.asarray(value_for_cost[1])
    y = (np.real(raw_y) if np.iscomplexobj(raw_y) else raw_y).astype(float).ravel()
    if x.size != y.size:
        raise ValueError(f"2D curve x/y size mismatch: {x.size} != {y.size}")

    data_range = definition.get("data_range", DEFAULT_DATA_RANGE)
    if not isinstance(data_range, (tuple, list)) or len(data_range) != 2:
        raise ValueError(f"invalid data_range: {data_range!r}")
    start, end = data_range
    if isinstance(start, str):
        mode = start.strip().upper()
        if mode == ALL:
            values = y[np.isfinite(y)]
        elif mode in {FIRST, LAST}:
            count = int(end)
            if count <= 0:
                raise ValueError(f"{mode} data_range must use a positive count: {data_range!r}")
            values = y[:count] if mode == FIRST else y[-count:]
            values = values[np.isfinite(values)]
        else:
            raise ValueError(f"unsupported data_range mode: {data_range!r}")
    else:
        low, high = sorted((float(start), float(end)))
        finite = np.isfinite(x) & np.isfinite(y)
        endpoints_exist = bool(np.any(x == low) and np.any(x == high))
        range_mask = (
            (x >= low) & (x <= high)
            if endpoints_exist
            else (x > low) & (x < high)
        )
        values = y[finite & range_mask]
    if values.size == 0:
        raise ValueError(f"no finite data selected for data_range={tuple(data_range)!r}")

    goal = float(definition["goal"])
    worst = float(definition["worst"])
    ext_ratio = float(definition.get("ext_ratio", 0.7))
    extreme = float(values.max() if goal < worst else values.min())
    combined_value_for_cost = ext_ratio * extreme + (1.0 - ext_ratio) * float(values.mean())
    return soft_cost(combined_value_for_cost, goal=goal, worst=worst, **curve)


def calculate_registered_cost(
    definition: Mapping[str, object],
    value_for_cost: Mapping[str, object],
    calculators: Mapping[str, object],
    **curve,
) -> float:
    selected_value_for_cost = value_for_cost[str(definition["value_for_cost"])]
    calculator_name = definition.get("calculator")
    if calculator_name is None:
        return soft_cost(
            float(selected_value_for_cost),
            goal=float(definition["goal"]),
            worst=float(definition["worst"]),
            **curve,
        )
    calculator = calculators.get(str(calculator_name))
    if not callable(calculator):
        raise ValueError(f"unknown cost calculator: {calculator_name}")
    return float(calculator(selected_value_for_cost, definition, **curve))


def calculate_defined_costs(
    definitions: Sequence[Mapping[str, object]],
    value_for_cost: Mapping[str, object],
    calculators: Mapping[str, object],
    **curve,
) -> tuple[float, ...]:
    return tuple(
        calculate_registered_cost(definition, value_for_cost, calculators, **curve)
        for definition in definitions
    )


def calculate_costs(
    samples: Sequence[Sequence[object]],
    calculate_sample_cost: Callable[[Sequence[object], RawVariables | None], Sequence[float]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    sample_rows = tuple(samples)
    variable_rows = (None,) * len(sample_rows) if raw_variables is None else tuple(raw_variables)
    if len(variable_rows) != len(sample_rows):
        raise ValueError(f"expected {len(sample_rows)} variable rows, got {len(variable_rows)}")
    return tuple(
        tuple(float(value) for value in calculate_sample_cost(sample, variables))
        for sample, variables in zip(sample_rows, variable_rows)
    )


def error_costs(objective_count: int, *, error_cost: float = 1.0) -> tuple[float, ...]:
    return (float(error_cost),) * int(objective_count)


def constraint_expressions(parameter_config) -> tuple[str, ...]:
    return tuple(
        expression
        for expression in getattr(parameter_config, "CONSTRAINTS", ())
        if isinstance(expression, str) and expression.strip()
    )


def constraint_cost(
    raw_variables: RawVariables | None,
    parameter_config,
    **curve,
) -> float:
    constraints = constraint_expressions(parameter_config)
    if not constraints:
        return 0.0
    if raw_variables is None:
        return float(curve.get("error_cost", 1.0))

    parameters = parameter_config.get_parameters()
    if isinstance(raw_variables, Mapping):
        values = {str(name): float(value) for name, value in raw_variables.items()}
    else:
        raw_values = tuple(float(value) for value in raw_variables)
        if len(raw_values) != len(parameters):
            raise ValueError(f"expected {len(parameters)} variables, got {len(raw_values)}")
        values = {parameter.name: value for parameter, value in zip(parameters, raw_values)}

    scope = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    scope.update({"abs": abs, "min": min, "max": max, "pow": pow, "round": round})
    scope.update(
        {
            name: value
            for name, value in vars(parameter_config).items()
            if not name.startswith("_") and isinstance(value, (int, float, bool))
        }
    )
    scope.update(values)
    scope["__get_var__"] = lambda name: float(scope[name] if name in scope else scope[f"${name}"])

    violations = [
        min(0.0, float(eval(_normalize_constraint_expression(expression), {"__builtins__": {}}, scope)))
        for expression in constraints
    ]
    return mean_cost(
        tuple(soft_cost(value, goal=0.0, worst=-1.0, **curve) for value in violations),
        error_cost=float(curve.get("error_cost", 1.0)),
    )


def _normalize_constraint_expression(expression: str) -> str:
    return _DOLLAR_VAR_RE.sub(
        lambda match: f"__get_var__({match.group(1)!r})",
        expression.replace("^", "**"),
    )
