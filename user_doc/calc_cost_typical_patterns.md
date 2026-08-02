# Typical `calc_cost.py` Patterns

`calc_cost.py` turns one sample's rawData into objective costs. It is used after
rawData has been recorded, and it is also used by the surrogate path. Keep it pure
and repeatable: the same rawData and same code should produce the same cost.

Keep only code that can change with the optimization task: rawData interpretation,
objective definitions, physical thresholds, custom calculators, and importance
regions. Reusable loading, axis reduction, definition dispatch, worst-curve
aggregation, constraints, failure fallback, weight allocation, and objective
counting belong in `yadof.job_template`; call those helpers instead of copying their
implementations into `calc_cost.py`.

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

The canonical scalar mapping is `soft_cost()`. It uses a tanh curve, handles either
physical direction, and bounds every finite valid result to `[0, 1]`. With the
default `edge_cost=0.1`, `goal` maps to `0.1`, `worst` maps to `0.9`, and values
beyond those thresholds smoothly saturate toward `0` or `1`. Set
`error_cost=1.0`; do not use a value above one merely to distinguish failure. A
framework execution failure can still produce an `inf` sentinel, which is separate
from task-level cost calculation.

The `0.1`/`0.9` anchor mapping is intentional. `goal` and `worst` express the
expected useful physical range, but task authors may choose them conservatively or
the simulator may produce values outside that range. Reserving `(0, 0.1)` and
`(0.9, 1)` lets the tanh tails keep ordering unexpectedly good and unexpectedly bad
finite results, so the optimizer still receives a direction of improvement. If the
anchors were mapped to exact `0`/`1` by clipping or linear rescaling, every value
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

If surrogate training should give extra attention to objective-relevant rawData
positions, also provide the optional weighting hook:

```python
def rawdata_importance_weights(sample_rawdata, *, floor=0.25, boost=2.0):
    ...
```

This hook does not decide which rawData is saved or included in the surrogate
training bundle. It only assigns relative weights to already modeled numeric
positions.

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
    build_rawdata_importance_weights,
)

ERROR_COST = 1.0

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

## RawData Importance Weights

A “gain importance mask” is the numeric weight array returned for a gain rawData
field by `rawdata_importance_weights()`. It has the same shape as that field's main
numeric array. It is not an inclusion mask.

| Question | Owning mechanism |
|---|---|
| Which far-field values are produced and saved? | `workflow.py` and its full rawData array |
| Which saved evidence is available for surrogate modeling? | Compatible recorded rawData and the surrogate training bundle |
| Which modeled positions receive more training attention? | `calc_cost.py:rawdata_importance_weights()` |

The framework behavior is:

- With no hook, modeled positions receive uniform weight.
- `build_rawdata_importance_weights()` initializes every position to `floor` and
  passes `floor + boost` to the task callback as `important`.
- When a field is small enough to use every query in a training step, these values
  weight the surrogate loss. When a large field uses stochastic query minibatches,
  they are used as query-sampling probabilities instead of weighting the sampled
  loss a second time.
- A positive `floor` preserves attention outside the important window. Setting it
  to zero can remove non-important positions from loss or stochastic sampling.
- The surrogate still reconstructs the full compatible rawData field for public
  prediction. Constant numeric slots are preserved from the rawData template rather
  than learned.

The important region should normally mirror the positions actually read by
`calculate_cost()`. For example, if gain cost uses a frequency band only at one
`Phi` and one `Theta`, mark the intersection of all three selectors:

```python
import numpy as np

from yadof.job_template.rawdata_contract import (
    angle_to_degrees,
    build_rawdata_importance_weights,
    frequency_to_ghz,
)

GAIN_RAWDATA_NAME = "far_field_gain"
GAIN_FREQUENCY_RANGE_GHZ = (2.4, 2.5)
TARGET_PHI_DEG = 0.0
TARGET_THETA_DEG = 0.0
ANGLE_TOLERANCE_DEG = 0.5


def _mark_gain_cost_window(view, weights, important):
    if view.name != GAIN_RAWDATA_NAME:
        return
    required_axes = ("Freq", "Phi", "Theta")
    if not all(view.has_axis(name) for name in required_axes):
        return

    try:
        selectors = [
            np.arange(size, dtype=int)
            for size in weights.shape
        ]
        selectors[view.axis_index("Freq")] = view.range_indices(
            "Freq",
            *GAIN_FREQUENCY_RANGE_GHZ,
            converter=frequency_to_ghz,
        )
        selectors[view.axis_index("Phi")] = np.asarray(
            [
                view.nearest_index(
                    "Phi",
                    TARGET_PHI_DEG,
                    ANGLE_TOLERANCE_DEG,
                    period=360.0,
                    converter=angle_to_degrees,
                )
            ],
            dtype=int,
        )
        selectors[view.axis_index("Theta")] = np.asarray(
            [
                view.nearest_index(
                    "Theta",
                    TARGET_THETA_DEG,
                    ANGLE_TOLERANCE_DEG,
                    converter=angle_to_degrees,
                )
            ],
            dtype=int,
        )
    except ValueError:
        return
    if all(indices.size for indices in selectors):
        weights[np.ix_(*selectors)] = important


def rawdata_importance_weights(sample_rawdata, *, floor=0.25, boost=2.0):
    return build_rawdata_importance_weights(
        sample_rawdata,
        _mark_gain_cost_window,
        floor=floor,
        boost=boost,
    )
```

Reuse the same target constants, unit converters, tolerances, and range semantics in
cost extraction and importance selection. `np.ix_()` is important here because it
forms the Cartesian intersection independently of rawData axis order.

`mark_axis_range()` is appropriate only when every value along the other axes is
also objective-relevant. It broadcasts across all remaining axes. For example,
marking only a `Freq` range in a `Freq × Phi × Theta` gain array boosts every
`Phi × Theta` point in that frequency range, not just the angle used by cost. The
helper also marks the complete array when the named axis is absent, so guard it
with `view.has_axis()` when that fallback is not intended.

If the instruction is “make the surrogate model all saved far-field rawData,” save
the full field in `workflow.py`; no importance hook is required for inclusion. Add
the hook only when there is a known objective-relevant region that deserves extra
attention. If no positions deserve more attention than others, omit the hook and
use uniform weights.

## What Not To Do

- Do not read or write job folders from `calc_cost.py`.
- Do not depend on `cost.json`.
- Do not save cost as a source file.
- Do not mutate rawData while calculating cost.
- Do not return physical values or unit-bearing objective names as costs; map every
  physical metric independently into `[0, 1]` with fixed task thresholds.
- Do not normalize against observed history, a population, or a batch.
- Do not clip physical metrics at `goal`/`worst` or remap the default `0.1`/`0.9`
  anchors to hard `0`/`1` endpoints; preserve informative tanh tails.
- Do not hide missing rawData by returning a normal-looking good cost. Return the configured error cost on calculation failure.
- Do not reimplement reusable yadof cost/rawData helpers or objective counting in
  the task module.
