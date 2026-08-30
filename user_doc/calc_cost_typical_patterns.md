# Typical `calc_cost.py` Patterns

Workspace `submit/calc_cost.py` turns one sample's rawData into objective costs. It is used after
rawData has been recorded, and it is also used by the surrogate path. Keep it pure
and repeatable: the same rawData and same code should produce the same cost.

Keep only code that can change with the optimization task: rawData interpretation,
objective definitions, physical thresholds, and custom calculators. Reusable
loading, axis reduction, definition dispatch, worst-curve aggregation, constraints,
failure fallback, and objective counting belong in `yadof.job_template`; call those
helpers instead of copying their implementations into `calc_cost.py`.

The reusable helpers are deliberately coarse-grained. A custom grouping whose
members carry task-specific ranges, a simulator-specific array layout, or another
narrow objective convention remains a local calculator passed through the generic
calculator registry. Do not add it to yadof solely to shorten one task file.

## Normalized Cost Contract

Every newly authored objective must be a dimensionless minimization cost in
`[0, 1]`: `0` is best and `1` is worst. Normalize each objective independently so
microseconds, MHz, dB, metres, and other physical magnitudes never compete merely
because their units have different numeric scales. Objective names should describe
the cost, such as `cost_lock_time` and `cost_frequency_error`; physical units belong
in rawData metadata, extracted variable names, and threshold constants.

Use fixed, task-owned physical `goal` and `worst` thresholds. Do not calculate a
minimum and maximum from recorded history, the current population, or the current
batch: history-dependent scaling would change the cost of identical rawData over
time and would also make real and surrogate paths depend on unrelated samples.

The canonical scalar mapping is `soft_cost()`. It uses a fixed-`p=2` algebraic
sigmoid, handles either physical direction, and bounds every finite valid result to
`[0, 1]`. With the default `edge_cost=0.1`, `goal` maps to `0.1`, `worst` maps to
`0.9`, and values beyond those thresholds slowly approach `0` or `1`. Set
`error_cost=1.0`; do not use a value above one merely to distinguish failure. A
framework execution failure can still produce an `inf` sentinel, which is separate
from task-level cost calculation.

For normalized centered position
`x = (value - goal) / (worst - goal) - 0.5`, the mapping is
`cost = 0.5 * (1 + a*x / sqrt(1 + (a*x)**2))`. The fixed power is `p=2`.
Unless `algebraic_scale=a` is supplied explicitly, `soft_cost()` derives
`a = (1 - 2*edge_cost) / sqrt(edge_cost * (1 - edge_cost))`; therefore the
default `edge_cost=0.1` uses `a=8/3` and preserves the `0.1`/`0.9` anchors.

The `0.1`/`0.9` anchor mapping is intentional. `goal` and `worst` express the
expected useful physical range, but task authors may choose them conservatively or
the simulator may produce values outside that range. Reserving `(0, 0.1)` and
`(0.9, 1)` lets the algebraic tails keep ordering unexpectedly good and unexpectedly
bad finite results, so the optimizer still receives a direction of improvement. If
the anchors were mapped to exact `0`/`1` by clipping or linear rescaling, every value
beyond either anchor would collapse onto a flat plateau and could no longer guide
selection. Therefore:

- do not clip the physical metric to the interval between `goal` and `worst`;
- do not rescale `soft_cost()` so the two anchors become exact `0` and `1`;
- treat `0` and `1` as the bounded tail limits, and `0.1`/`0.9` as the default
  anchor costs;
- keep `error_cost=1.0`, so invalid task data is no better than finite results in
  the upper tail.

For example, with `goal=2 us` and `worst=10 us`, a simulated `15 us` result maps
above `0.9` but normally below `1.0`. A later `12 us` result is therefore recognized
as an improvement even though both exceeded the original conservative `worst`.

`calculate_task_cost()` and its registered scalar/curve calculators already call
`soft_cost()`. For a custom `calculate_rawdata_cost()` callback, normalize the
physical metrics explicitly:

```python
from yadof.job_template.cost_misc import calculate_rawdata_cost, soft_cost

OBJECTIVE_NAMES = ("cost_lock_time", "cost_frequency_error")
ERROR_COST = 1.0


def _calculate_loaded_cost(loaded_items, raw_variables):
    lock_time_us = ...
    frequency_error_mhz = ...
    return (
        soft_cost(
            lock_time_us,
            goal=2.0,
            worst=10.0,
            error_cost=ERROR_COST,
        ),
        soft_cost(
            frequency_error_mhz,
            goal=0.1,
            worst=5.0,
            error_cost=ERROR_COST,
        ),
    )


def calculate_cost(sample_rawdata, raw_variables=None):
    return calculate_rawdata_cost(
        sample_rawdata,
        raw_variables,
        objective_names=OBJECTIVE_NAMES,
        calculate_loaded_cost=_calculate_loaded_cost,
        error_cost=ERROR_COST,
    )
```

Choose scientific thresholds from the task specification or ask the user when they
are unknown. Do not silently infer them from whichever results are currently
available. Depart from this normalized contract only when the user explicitly asks
for another scale and the workspace records the reason.

## Required Public Functions

At minimum, provide:

```python
def calculate_cost(sample_rawdata, raw_variables=None) -> tuple[float, ...]:
    ...


def get_objective_names() -> tuple[str, ...]:
    ...
```

Do not define `get_objective_count()` merely as `len(get_objective_names())`; yadof
derives and validates the count from objective names.

Do not define `rawdata_importance_weights()`. That former hook has been removed:
all varying numeric rawData fields use the package-owned real-only,
field-balanced training policy. `yadof check` rejects a remaining hook with an
actionable diagnostic.

Installed workspace calls load these functions through `yadof.job_template`; the
installed runtime uses the matching `yadof.job_template` gateway.

## Typical Structure

The current project style separates cost calculation into four parts:

1. Load rawData into `RawDataView` objects.
2. Extract task-specific `value_for_cost` values.
3. Define objectives in `COST_DEFINITIONS`.
4. Call the yadof defined-cost helper to apply reusable minimization, constraint,
   and failure behavior.

Example:

```python
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from . import parameters_constraints as parameter_config
from yadof.job_template.cost_misc import (
    ALL,
    RawVariables,
    calculate_task_cost,
    objective_names_from_definitions,
)
from yadof.job_template.rawdata_contract import (
    RawDataItem,
    RawDataView,
)

ERROR_COST = 1.0

COST_CURVE = {"error_cost": ERROR_COST, "edge_cost": 0.1, "algebraic_scale": None}
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

def _extract_value_for_cost(loaded_items: Sequence[RawDataView]) -> dict[str, object]:
    curve = next(item for item in loaded_items if item.name == "response_curve")
    x = curve.axis_coordinates("x") if curve.has_axis("x") else np.arange(curve.data.size)
    y = np.asarray(curve.data, dtype=float).ravel()
    return {"response_curve": (x, y)}


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
    return calculate_task_cost(
        sample_rawdata,
        raw_variables,
        definitions=COST_DEFINITIONS,
        extract_value_for_cost=_extract_value_for_cost,
        parameter_config=parameter_config,
        cost_curve=COST_CURVE,
        constraint_curve=CONSTRAINT_COST_CURVE,
    )


def get_objective_names() -> tuple[str, ...]:
    return objective_names_from_definitions(
        COST_DEFINITIONS,
        parameter_config,
    )
```

## Cost Direction

yadof expects minimization costs. Smaller is better.

The helper `soft_cost(value_for_cost, goal, worst, ...)` maps values near `goal` toward
low cost and values near `worst` toward high cost. It handles both directions:

- If `goal < worst`, lower physical values are better.
- If `goal > worst`, higher physical values are better.

With the example curve settings above, the goal maps to `0.1`, the worst value maps
to `0.9`, better/worse values saturate toward the normalized `0`/`1` limits, and
invalid task data maps to `ERROR_COST = 1.0`.

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

## Surrogate Training Ownership

`workflow.py` owns which rawData is produced and saved. Compatible recorded varying
numeric slots enter surrogate modeling; constant slots remain in the reconstruction
template. `calc_cost.py` owns only current rawData interpretation and objectives—it
does not select, weight, rank, or mask surrogate training positions.

Real-evaluation rawData is committed before this callback runs. If the process is
lost or the callback fails, yadof may invoke it again for the same evidence under a
later task snapshot. Keep it deterministic and replay-safe: use only the supplied
rawData/raw variables plus task constants, do not mutate rawData, and do not perform
irreversible external writes. Every returned objective must be numeric and finite,
and the tuple width must match `get_objective_names()`; callback exceptions, width
mismatch, `NaN`, and infinity are interpretation failures rather than evidence
loss.

For large rawData, the package may sample a bounded number of queries per step.
That sampler balances active fields and samples without replacement inside each
field. The loss averages pointwise Smooth L1 within each field and then averages
fields equally, so duplicating scalar positions in one field does not increase that
field's macro influence.

## What Not To Do

- Do not read or write job folders from `calc_cost.py`.
- Do not depend on `cost.json`.
- Do not save cost as a source file.
- Do not mutate rawData while calculating cost.
- Do not rely on one-shot external side effects; the same committed evidence may be
  interpreted more than once.
- Do not return physical values or unit-bearing objective names as costs; map every
  physical metric independently into `[0, 1]` with fixed task thresholds.
- Do not normalize against observed history, a population, or a batch.
- Do not clip physical metrics at `goal`/`worst` or remap the default `0.1`/`0.9`
  anchors to hard `0`/`1` endpoints; preserve informative algebraic tails.
- Do not hide missing rawData by returning a normal-looking good cost. Return the configured error cost on calculation failure.
- Do not reimplement reusable yadof cost/rawData helpers or objective counting in
  the task module.
