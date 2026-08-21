"""Reusable, task-agnostic cost calculation helpers."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Callable

import numpy as np

from .rawdata_contract import (
    RawDataContractError,
    RawDataItem,
    RawDataView,
    load_rawdata_views,
)

RawVariables = Mapping[str, float] | Sequence[float]

ALL = "ALL"
FIRST = "FIRST"
LAST = "LAST"
DEFAULT_DATA_RANGE = (ALL, 0)

COST_CALCULATION_ERRORS = (
    KeyError,
    ValueError,
    IndexError,
    TypeError,
    FloatingPointError,
)
CONSTRAINT_CALCULATION_ERRORS = COST_CALCULATION_ERRORS + (NameError, SyntaxError)

_DOLLAR_VAR_RE = re.compile(r"\$([A-Za-z_]\w*)")


def soft_cost(
    value_for_cost: float,
    goal: float,
    worst: float,
    *,
    error_cost: float = 1.0,
    edge_cost: float = 0.1,
    algebraic_scale: float | None = None,
) -> float:
    """Map one physical minimization metric to a bounded algebraic cost.

    The centered physical position ``x`` is transformed with the fixed-power
    algebraic sigmoid ``a*x / sqrt(1 + (a*x)**2)``, then scaled and biased into
    ``[0, 1]``. With the default scale, ``goal`` maps to ``edge_cost`` and
    ``worst`` maps to ``1 - edge_cost``; values beyond those thresholds approach
    zero or one with slow algebraic tails. The thresholds are calibration anchors,
    not clipping bounds, so unexpectedly good or bad finite values retain ordering.
    Set ``error_cost=1.0`` when task-level failures must preserve the normalized-
    cost contract.
    """

    if value_for_cost is False or value_for_cost is None:
        return float(error_cost)
    value, goal, worst = float(value_for_cost), float(goal), float(worst)
    edge = float(edge_cost)
    if (
        not (math.isfinite(value) and math.isfinite(goal) and math.isfinite(worst))
        or goal == worst
        or not (0.0 < edge < 0.5)
    ):
        return float(error_cost)
    scale = (
        (1.0 - 2.0 * edge) / math.sqrt(edge * (1.0 - edge))
        if algebraic_scale is None
        else float(algebraic_scale)
    )
    if not (math.isfinite(scale) and scale > 0.0):
        return float(error_cost)
    position = (value - goal) / (worst - goal)
    scaled_position = scale * (position - 0.5)
    if math.isinf(scaled_position):
        algebraic_value = math.copysign(1.0, scaled_position)
    else:
        # hypot(1, z) is the stable p=2 denominator sqrt(1 + abs(z)**2).
        algebraic_value = scaled_position / math.hypot(1.0, scaled_position)
    return float((algebraic_value + 1.0) / 2.0)


def mean_cost(values: Sequence[float], *, error_cost: float = 1.0) -> float:
    finite = tuple(float(value) for value in values if math.isfinite(float(value)))
    return sum(finite) / len(finite) if finite else float(error_cost)


def calculate_2d_curve_cost(
    value_for_cost: object,
    definition: Mapping[str, object],
    **curve,
) -> float:
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
                raise ValueError(
                    f"{mode} data_range must use a positive count: {data_range!r}"
                )
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
    combined = ext_ratio * extreme + (1.0 - ext_ratio) * float(values.mean())
    return soft_cost(combined, goal=goal, worst=worst, **curve)


def calculate_worst_curve_cost(
    value_for_cost: object,
    definition: Mapping[str, object],
    **curve,
) -> float:
    """Return the largest cost across a task-provided sequence of curves."""

    if not isinstance(value_for_cost, Sequence) or isinstance(
        value_for_cost, (str, bytes)
    ):
        raise ValueError("worst-curve cost requires a sequence of curves")
    costs = tuple(
        calculate_2d_curve_cost(item, definition, **curve)
        for item in value_for_cost
    )
    if not costs:
        raise ValueError("worst-curve cost requires at least one curve")
    return float(max(costs))


def calculate_registered_cost(
    definition: Mapping[str, object],
    value_for_cost: Mapping[str, object],
    calculators: Mapping[str, object],
    **curve,
) -> float:
    selected = value_for_cost[str(definition["value_for_cost"])]
    calculator_name = definition.get("calculator")
    if calculator_name is None:
        return soft_cost(
            float(selected),
            goal=float(definition["goal"]),
            worst=float(definition["worst"]),
            **curve,
        )
    calculator = calculators.get(str(calculator_name))
    if not callable(calculator):
        raise ValueError(f"unknown cost calculator: {calculator_name}")
    return float(calculator(selected, definition, **curve))


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


def objective_names_from_definitions(
    definitions: Sequence[Mapping[str, object]],
    parameter_config: object | None = None,
    *,
    constraint_name: str = "cost_constraints",
) -> tuple[str, ...]:
    """Derive task objective names and the standard optional constraint objective."""

    names = tuple(str(definition["name"]) for definition in definitions)
    if parameter_config is not None and constraint_expressions(parameter_config):
        names += (str(constraint_name),)
    return names


def calculate_task_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None,
    *,
    definitions: Sequence[Mapping[str, object]],
    extract_value_for_cost: Callable[
        [Sequence[RawDataView]], Mapping[str, object]
    ],
    parameter_config: object | None = None,
    calculators: Mapping[str, object] | None = None,
    cost_curve: Mapping[str, object] | None = None,
    constraint_curve: Mapping[str, object] | None = None,
) -> tuple[float, ...]:
    """Apply the invariant defined-cost, constraint, and failure policy."""

    curve = dict(cost_curve or {})
    constraint_settings = dict(curve if constraint_curve is None else constraint_curve)
    registry: dict[str, object] = {
        "calculate_2d_curve_cost": calculate_2d_curve_cost,
        "calculate_worst_curve_cost": calculate_worst_curve_cost,
    }
    registry.update(calculators or {})
    names = objective_names_from_definitions(definitions, parameter_config)
    error_cost = float(curve.get("error_cost", 1.0))
    try:
        loaded_items = load_rawdata_views(sample_rawdata)
        costs = calculate_defined_costs(
            definitions,
            extract_value_for_cost(loaded_items),
            registry,
            **curve,
        )
    except COST_CALCULATION_ERRORS as exc:
        if isinstance(exc, RawDataContractError):
            raise
        return error_costs(len(names), error_cost=error_cost)

    if parameter_config is None or not constraint_expressions(parameter_config):
        return costs
    try:
        return costs + (
            constraint_cost(
                raw_variables,
                parameter_config,
                **constraint_settings,
            ),
        )
    except CONSTRAINT_CALCULATION_ERRORS:
        return costs + (
            float(constraint_settings.get("error_cost", error_cost)),
        )


def calculate_rawdata_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None,
    *,
    objective_names: Sequence[str],
    calculate_loaded_cost: Callable[
        [Sequence[RawDataView], RawVariables | None], Sequence[float]
    ],
    error_cost: float = float("inf"),
) -> tuple[float, ...]:
    """Apply invariant loading, width validation, and failure fallback."""

    names = tuple(str(name) for name in objective_names)
    try:
        loaded_items = load_rawdata_views(sample_rawdata)
        costs = tuple(
            float(value)
            for value in calculate_loaded_cost(loaded_items, raw_variables)
        )
        if len(costs) != len(names):
            raise ValueError(
                f"expected {len(names)} costs, got {len(costs)}"
            )
        return costs
    except COST_CALCULATION_ERRORS as exc:
        if isinstance(exc, RawDataContractError):
            raise
        return error_costs(len(names), error_cost=error_cost)


def strict_finite_mean(
    values: object,
    *,
    error_cost: float = float("inf"),
) -> float:
    """Return the mean only when every selected value is finite."""

    selected = np.asarray(values, dtype=float)
    if selected.size == 0 or not np.all(np.isfinite(selected)):
        return float(error_cost)
    return float(np.mean(selected))


def calculate_costs(
    samples: Sequence[Sequence[object]],
    calculate_sample_cost: Callable[
        [Sequence[object], RawVariables | None], Sequence[float]
    ],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    sample_rows = tuple(samples)
    variable_rows = (
        (None,) * len(sample_rows) if raw_variables is None else tuple(raw_variables)
    )
    if len(variable_rows) != len(sample_rows):
        raise ValueError(
            f"expected {len(sample_rows)} variable rows, got {len(variable_rows)}"
        )
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
        values = {
            parameter.name: value for parameter, value in zip(parameters, raw_values)
        }

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
    scope["__get_var__"] = lambda name: float(
        scope[name] if name in scope else scope[f"${name}"]
    )
    violations = [
        min(
            0.0,
            float(
                eval(
                    _normalize_constraint_expression(expression),
                    {"__builtins__": {}},
                    scope,
                )
            ),
        )
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


__all__ = [
    "ALL",
    "CONSTRAINT_CALCULATION_ERRORS",
    "COST_CALCULATION_ERRORS",
    "DEFAULT_DATA_RANGE",
    "FIRST",
    "LAST",
    "RawVariables",
    "calculate_2d_curve_cost",
    "calculate_costs",
    "calculate_defined_costs",
    "calculate_rawdata_cost",
    "calculate_registered_cost",
    "calculate_task_cost",
    "calculate_worst_curve_cost",
    "constraint_cost",
    "constraint_expressions",
    "error_costs",
    "mean_cost",
    "objective_names_from_definitions",
    "soft_cost",
    "strict_finite_mean",
]
