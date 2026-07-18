# Typical `calc_cost.py` Patterns

`calc_cost.py` turns one sample's rawData into objective costs. It is used after
rawData has been recorded, and it is also used by the surrogate path. Keep it pure
and repeatable: the same rawData and same code should produce the same cost.

## Required Public Functions

At minimum, provide:

```python
def calculate_cost(sample_rawdata, raw_variables=None) -> tuple[float, ...]:
    ...


def get_objective_names() -> tuple[str, ...]:
    ...


def get_objective_count() -> int:
    return len(get_objective_names())
```

If surrogate training should emphasize objective-relevant rawData windows, also
provide:

```python
def rawdata_importance_weights(sample_rawdata, *, floor=0.25, boost=2.0):
    ...
```

Installed workspace calls load these functions through `yadof.job_template`; the
transitional source runtime uses the matching `project/job_template/api.py` gateway.

## Typical Structure

The current project style separates cost calculation into four parts:

1. Load rawData into `RawDataView` objects.
2. Extract task-specific `value_for_cost` values.
3. Define objectives in `COST_DEFINITIONS`.
4. Convert extracted values into bounded minimization costs.

Example:

```python
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
        "name": "cost_response_peak",
        "value_for_cost": "response_curve",
        "goal": 0.2,
        "worst": 1.0,
        "ext_ratio": 0.7,
        "data_range": (ALL, 0),
        "calculator": "calculate_2d_curve_cost",
    },
)

SIMULATION_OBJECTIVE_NAMES = tuple(str(definition["name"]) for definition in COST_DEFINITIONS)


def _extract_value_for_cost(loaded_items: Sequence[RawDataView]) -> dict[str, object]:
    curve = next(item for item in loaded_items if item.name == "response_curve")
    x = curve.axis_coordinates("x") if curve.has_axis("x") else np.arange(curve.data.size)
    y = np.asarray(curve.data, dtype=float).ravel()
    return {"response_curve": (x, y)}


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
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
```

## Cost Direction

yadof expects minimization costs. Smaller is better.

The helper `soft_cost(value_for_cost, goal, worst, ...)` maps values near `goal` toward
low cost and values near `worst` toward high cost. It handles both directions:

- If `goal < worst`, lower physical values are better.
- If `goal > worst`, higher physical values are better.

With the example curve settings above, the goal maps near `0.1`, the worst value
maps near `0.9`, and invalid data maps to `ERROR_COST`.

## Common RawData Extraction Patterns

Select by rawData name:

```python
item = next(view for view in loaded_items if view.name == "response_curve")
```

Select an axis point:

```python
target_frequency = ...
frequency_tolerance = ...
cut = item.select("frequency_axis", target_frequency, frequency_tolerance, converter=frequency_to_ghz)
```

Select an angular point with wraparound:

```python
target_angle_degrees = ...
angle_tolerance_degrees = ...
angle_cut = item.select("angle_axis", target_angle_degrees, angle_tolerance_degrees, period=360.0, converter=angle_to_degrees)
```

Select an axis range:

```python
range_min = ...
range_max = ...
indices = item.range_indices("frequency_axis", range_min, range_max, converter=frequency_to_ghz)
```

Reduce leftover non-objective axes at cost time. Do not force the workflow to discard
full-field rawData unless the task intentionally needs only a trace.

## Constraints

Constraint expressions live in `parameters_constraints.py`.

Each expression should evaluate to:

- `>= 0` when satisfied,
- `< 0` when violated.

When any constraint exists, `get_objective_names()` appends `cost_constraints`.
If a constraint expression cannot be evaluated, the constraint cost becomes
`ERROR_COST`.

## RawData Importance Weights

Surrogate training can use task-owned weights to care more about objective-relevant
rawData windows while still retaining full-field coverage.

Example:

```python
def rawdata_importance_weights(sample_rawdata, *, floor=0.25, boost=2.0):
    out = []
    for item in sample_rawdata:
        view = RawDataView.from_item(item)
        weights = np.full(np.asarray(view.data).shape, float(floor), dtype=np.float32)
        if view.name == "response_curve" and view.has_axis("x"):
            from .rawdata_contract import mark_axis_range

            mark_axis_range(weights, view, "x", 0.4, 0.6, floor + boost)
        out.append({view.data_key: weights})
    return tuple(out)
```

If you do not know which rawData points are more important, omit this hook. The
framework can still train on all rawData.

## What Not To Do

- Do not read or write job folders from `calc_cost.py`.
- Do not depend on `cost.json`.
- Do not save cost as a source file.
- Do not mutate rawData while calculating cost.
- Do not hide missing rawData by returning a normal-looking good cost. Return the configured error cost on calculation failure.
