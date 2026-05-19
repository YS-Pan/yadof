# NSGA-III + Surrogate Optimization Handoff

Date: 2026-05-19

This document is a handoff note for a future AI agent that will implement code
changes in this repository. The current task is analysis and planning only; no
project code has been modified for this note.

The user wants to fully switch the optimizer to NSGA-III. Backward
compatibility with NSGA-II is not required. The user also wants the surrogate
changes discussed below to be considered, because the current surrogate-assisted
run loses an important tradeoff branch.

## Required Reading Order

Before implementing, read these files in full:

1. `dev_doc/README.md`
2. `dev_doc/spec 20260502.md`
3. Every file in `dev_doc/architecture/`
4. `dev_doc/reference_map.md`
5. `dev_doc/terminology.md`

Then list prompt files under:

```text
dev_doc/prompt/
dev_doc/prompt/10_modules/
```

For this task, read at least:

```text
dev_doc/prompt/00_project.md
dev_doc/prompt/10_modules/optimize.md
dev_doc/prompt/10_modules/surrogate.md
dev_doc/prompt/10_modules/job_template.md
dev_doc/prompt/10_modules/recorded_data.md
dev_doc/prompt/10_modules/config.md
dev_doc/prompt/10_modules/tests.md
```

Follow the documentation rules in `dev_doc/README.md`: after code changes,
update relevant architecture and prompt files, add a change record, and update
terminology if the change introduces or clarifies a non-obvious term.

## Current Project Constraints

The central invariant is:

```text
normalized variables -> rawData -> job_template/calc_cost.py -> cost
```

Do not replace the surrogate with a direct `variables -> cost` model. The
surrogate may use cost-aware auxiliary losses, but its public prediction path
must still predict rawData first and calculate cost from predicted rawData.

Core modules should communicate through public `api.py` files. `config.py` may
be imported directly.

## User's Observed Problem

The user ran two independent optimization campaigns based on `test_com`.

Without surrogate:

- Population size: 500.
- Generations: 20.
- Best combined-cost individuals had `obj1` and `obj3` near zero, often below
  `0.1`.
- `obj2` was worse, around `0.3`.
- Plot saved at `project/tools/cost_20260518_083401.png`.

With surrogate:

- `OPTIMIZE_SURROGATE_ALPHA = 3`.
- `OPTIMIZE_SURROGATE_BETA = 3`.
- Population size: 500.
- The average cost reached the previous 10000-evaluation level at roughly 3000
  real evaluations.
- After that, optimization appeared to converge.
- Converged direction was different: `obj1` and `obj2` near zero, while `obj3`
  remained around `0.5`.
- Diversity was much worse. The population contained almost only the
  `obj1/obj2 good, obj3 bad` branch.
- The current `project/recorded_data/` is from the surrogate-assisted run.

For this document, use these shorthand labels:

```text
A branch: obj1 good, obj3 good, obj2 bad
B branch: obj1 good, obj2 good, obj3 bad
```

The user's hypothesis is that the surrogate cannot accurately fit the fields
for A-branch individuals. The analysis below supports that hypothesis and adds
several implementation-level causes.

## Quantitative Evidence From Analysis

The analysis used the current task definition:

```text
project/job_template/test_com.py
project/job_template/calc_cost.py
project/job_template/parameters_constraints.py
```

The current recorded surrogate run contains:

```text
completed records: 7429
generations present: 0 through 14
```

Using current `test_com` and `calc_cost` to recompute costs from raw variables:

```text
threshold = 0.1
A branch count: 0
B branch count: 1837
best combined cost: about 0.494255
best costs: (0.0077, 0.0098, 0.4767)
```

An in-memory, no-surrogate baseline was reproduced without writing jobs or
recorded_data. It used the existing baseline optimizer logic and direct
`test_com -> calc_cost` evaluation:

```text
population size: 500
generations: 20
total evaluations: 10000
threshold = 0.1
A branch count: 385
B branch count: 639
best combined cost: about 0.297576
best costs: (0.0169, 0.2806, 0.0)
```

This confirms that A-branch individuals exist in the true task and the
non-surrogate optimizer can find them.

The latest saved surrogate checkpoint was loaded without retraining:

```text
project/surrogate/checkpoints/generation_0014.json
sample_count: 6998
reported mean_relative_error: 0.0
```

Representative predictions from that checkpoint:

```text
A branch true:      (0.0169, 0.2806, 0.0)
A branch predicted: (0.5785, 0.9713, 0.6687)

B branch true:      (0.0189, 0.0125, 0.4724)
B branch predicted: (0.0764, 0.0129, 0.5088)
```

Aggregate random subset check:

```text
random 250 MAE by objective: [0.1861, 0.0728, 0.0839]

A true branch subset:
true mean: [0.0380, 0.8392, 0.0005]
pred mean: [0.5881, 0.9461, 0.7330]
MAE:       [0.5501, 0.1141, 0.7325]

B true branch subset:
true mean: [0.0329, 0.0406, 0.8114]
pred mean: [0.0988, 0.0471, 0.8075]
MAE:       [0.0659, 0.0127, 0.0284]
```

Therefore the surrogate is highly asymmetric: it fits the B branch much better
than the A branch.

## Current Code Areas Involved

Important files:

```text
project/optimize/gpsaf.py
project/optimize/gpsaf_pymoo.py
project/optimize/gpsaf_phases.py
project/optimize/gpsaf_misc.py
project/optimize/problem_info.py
project/surrogate/runtime.py
project/surrogate/modeling.py
project/config.py
project/job_template/calc_cost.py
project/job_template/test_com.py
project/job_template/api.py
project/recorded_data/query.py
```

Reference files with relevant ideas:

```text
reference/20260418 shorten/code/modeling.py
reference/20260418 shorten/code/objectives.py
reference/20260418 shorten/code/problem.py
reference/20260418 shorten/code/optimize_surrogate.py
reference/20260418 shorten/code/surrogate_runtime.py
reference/20260418 shorten/code/archive_store.py
reference/20260418 shorten/code/experiment_config.py
```

## Diagnosed Causes

### 1. Historical Surrogate Error Is Artificially Zero

In `project/surrogate/runtime.py`, after training, the state is built with:

```python
pred_costs = true_costs
mean_error = _mean_relative_error(true_costs, pred_costs)
```

This makes `mean_relative_error` exactly zero and makes
`evaluate_historical_errors()` report zero-like errors even when the model is
not accurate.

Observed non-snapped in-sample prediction error from the existing checkpoint:

```text
checkpoint reported mean_relative_error: 0.0
non-snapped train subset MAE: [0.1336, 0.0494, 0.0263]
median relative error: [0.5478, 0.1629, 0.0243]
```

This matters because `project/optimize/gpsaf_phases.py` uses historical errors
when doing noisy comparisons in beta phase. If historical error is zero, GPSAF
trusts surrogate predictions too much.

### 2. The Current Relative Loss Is Not Really Relative

In `project/surrogate/modeling.py`, the relative term uses:

```python
denom = y_batch.abs().clamp_min(1.0)
rel_loss = smooth_l1(pred / denom, y_batch / denom)
```

But `y_batch` is already min/range scaled in `project/surrogate/runtime.py`
before training. Scaled values are mostly in `[0, 1]`, so `clamp_min(1.0)` makes
the denominator almost always equal to 1. The relative loss degenerates into a
plain absolute loss.

The user's intended meaning of relative loss is:

```text
true = 0.1, error = 0.01
true = 1.0, error = 0.10

These should receive similar concern.
```

That corresponds to:

```text
relative_error = abs(pred - true) / max(abs(true), eps)
```

Use care: applying strong relative loss to every rawData pixel can overweight
near-zero background. Prefer relative loss on objective metrics or objective
costs first, and only apply rawData relative loss with a meaningful floor.

### 3. Surrogate Training Fits All RawData Points, But Cost Depends On Few Points

The current `calc_cost.py` only uses:

```text
summary values: 2 scalars
curve window: 12 points per curve channel, 2 channels -> 24 values
surface center window: 4 x 4 -> 16 values
total cost-relevant rawData values: 42
```

The surrogate models:

```text
curve values: 2 x 160 = 320
summary values: 2
surface values: 48 x 48 = 2304
total modeled values: 2626
```

Only about 1.6% of modeled rawData slots directly affect the current cost.

The user explicitly does not want to train only the cost-critical window. The
correct direction is:

- Keep full-field rawData reconstruction.
- Add extra weight or auxiliary losses for cost-critical metrics.
- Keep non-critical regions because they may carry information correlated with
  the critical region.

This matches the old reference approach: `reference/20260418 shorten` trains on
all query points, but also uses saliency/adaptive weights and objective-aware
loss terms.

Reference examples:

```text
reference/20260418 shorten/code/modeling.py:
- build_adaptive_weight_map()
- objective_metric_loss_weight
- objective_cost_loss_weight
- gradient/curvature losses for curves/surfaces/volumes

reference/20260418 shorten/code/experiment_config.py:
- importance_floor = 0.25
- objective_metric_loss_weight = 0.15
- objective_cost_loss_weight = 0.25
```

The key idea is that non-critical regions still have a floor weight, while
important regions and objective-derived quantities have additional weight.

### 4. Current GPSAF Selection Can Amplify Surrogate Bias

Current surrogate selection uses pairwise comparison in alpha phase and a beta
phase that advances a simulated optimizer on surrogate-predicted costs.

In `project/optimize/gpsaf_phases.py`:

- `run_alpha_phase()` generates alpha batches and compares candidates by
  position.
- `pick_record()` uses `better_costs()`.

In `project/optimize/gpsaf_misc.py`:

- `better_costs()` uses dominance first.
- If neither dominates, it compares total cost.

This tends to prefer one tradeoff direction when the surrogate systematically
underestimates that direction. It does not preserve Pareto diversity as well as
NSGA-style survival over a full candidate pool.

### 5. The A Branch Is Starved

Using current surrogate-run history through generation 13, a reconstructed
generation-14 alpha candidate pool of 1500 candidates contained:

```text
threshold = 0.1
A branch count: 0
B branch count: 610
```

That means the population dynamics have already collapsed around the B branch.
Once A samples disappear from real evaluations, the surrogate receives no new
A-branch corrections, so the loop self-reinforces.

## User Decision: Fully Switch To NSGA-III

The user wants a full switch to NSGA-III and does not require compatibility with
NSGA-II. Do not add a config switch to keep NSGA-II. Remove or replace NSGA-II
usage in the optimizer path.

The expected difference:

- NSGA-II preserves diversity using crowding distance.
- NSGA-III preserves diversity by associating candidates with reference
  directions and filling underrepresented directions.
- For 3 objectives, NSGA-III can explicitly maintain representatives across
  different objective tradeoff directions.
- NSGA-III will not by itself fix badly wrong surrogate predictions. It can
  only preserve diverse directions that survive the predicted-cost selection.

Therefore, the implementation should combine NSGA-III with improved surrogate
error calibration and objective-aware surrogate training.

## NSGA-III Implementation Guidance

### Dependency Notes

The project already uses `pymoo`. Use pymoo's NSGA-III implementation:

```python
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.util.ref_dirs import get_reference_directions
```

Check exact import names in the installed pymoo version before editing. If
imports differ, inspect local pymoo package docs/source in the environment.

### Files To Change

Primary:

```text
project/optimize/gpsaf_pymoo.py
project/optimize/gpsaf_phases.py
project/optimize/gpsaf.py
project/optimize/problem_info.py
project/config.py
```

Likely tests:

```text
project/test/test_surrogate_optimize_real.py
project/test/test_minimal_closed_loop.py
project/test/test_optimize_generations.py
new or updated tests under project/test/
```

Docs to update after code changes:

```text
dev_doc/architecture/c4_component.md
dev_doc/architecture/c4_container.md
dev_doc/architecture/4plus1_process_view.md
dev_doc/architecture/4plus1_development_view.md
dev_doc/prompt/10_modules/optimize.md
dev_doc/prompt/10_modules/config.md
dev_doc/prompt/10_modules/surrogate.md
dev_doc/prompt/00_project.md
dev_doc/change_records/<timestamp>_nsga3-surrogate-selection.md
```

### Replace NSGA2 With NSGA3

In `project/optimize/gpsaf_pymoo.py`, remove the NSGA2 import and use NSGA3 for
multi-objective problems.

Current logic uses:

```python
from pymoo.algorithms.moo.nsga2 import NSGA2
```

The target should use NSGA3 for objective_count >= 2.

Single-objective behavior can stay GA unless the user explicitly wants every
case to be NSGA-III. For this project's default test task there are 3
objectives, so the important path is multi-objective.

Recommended helper:

```python
def _reference_directions(objective_count: int, population_size: int) -> np.ndarray:
    ...
```

For 3 objectives and population around 500, Das-Dennis partitions of 30 produce
496 directions:

```text
C(30 + 3 - 1, 3 - 1) = 496
```

This is close to 500. There are two implementation choices:

1. Set `pop_size=len(ref_dirs)` and accept that a requested 500 becomes 496.
2. Keep `pop_size=500` with 496 reference directions.

Because the user wants population size 500, prefer keeping `pop_size` equal to
the requested size unless pymoo warns or behaves poorly. Add diagnostics showing
both requested population size and reference direction count.

For general objective counts, choose partitions so `len(ref_dirs)` is near the
requested population size. A simple search over `n_partitions` is enough:

```python
from math import comb

def _das_dennis_count(n_obj: int, partitions: int) -> int:
    return comb(partitions + n_obj - 1, n_obj - 1)
```

Pick the partition count whose direction count is closest to population size,
with a reasonable minimum of 1.

Potential config names:

```python
OPTIMIZE_NSGA3_REF_DIR_METHOD = "das-dennis"
OPTIMIZE_NSGA3_PARTITIONS = None
```

However, because the user requested no compatibility, do not add an algorithm
selection config. It is fine to add NSGA-III-specific tuning config.

### Diagnostics

Update optimizer diagnostics from:

```text
baseline_optimizer: pymoo.NSGA2
```

to:

```text
baseline_optimizer: pymoo.NSGA3
reference_direction_count: ...
reference_direction_partitions: ...
```

### Replace Surrogate Alpha Pairwise Selection

Switching only the base optimizer from NSGA2 to NSGA3 may not be enough, because
the current surrogate alpha phase does pairwise predicted-cost tournaments.

Recommended change: in `project/optimize/gpsaf_phases.py`, make alpha phase:

1. Generate `alpha * population_size` candidate records.
2. Predict all candidates with surrogate.
3. Select `population_size` records by NSGA-III survival over predicted costs.

This avoids position-wise alpha batch replacement and lets NSGA-III preserve
reference-direction diversity across the whole predicted candidate pool.

Implementation outline:

```python
def nsga3_survival_records(context, records, n_survive):
    # records have x and pred_costs
    # create pymoo Population with X and F
    # call NSGA3 survival or a prepared algorithm survival
    # map selected X rows back to records
```

Practical simpler route:

- Add a helper in `gpsaf_pymoo.py` that takes `CandidateRecord` rows with
  `pred_costs` and returns selected records.
- Reuse the same `UnitBoxProblem` and reference directions as the main
  algorithm.
- Be careful when mapping selected pymoo individuals back to records. The
  safest method is to store a record index on the Individual, e.g.
  `individual.set("record_index", idx)`.

### Beta Phase

The user asked for NSGA-III, not necessarily for removing beta. Two options:

1. Conservative: keep beta phase but use NSGA-III in the simulated optimizer
   state because `_make_algorithm()` now returns NSGA3.
2. Better: after beta generates additional surrogate-predicted candidates, pool
   anchors + beta candidates and run NSGA-III survival again.

Option 2 is more consistent with NSGA-III diversity and less likely to collapse
to a single branch.

If time is limited, implement option 1 first and add tests. Then consider
option 2.

### Exploration Quota

Even with NSGA-III, surrogate bias can still eliminate A-branch candidates.
Strong recommendation: reserve a small real-evaluation quota for baseline
NSGA-III offspring or random/novel candidates that bypass surrogate selection.

Example:

```text
OPTIMIZE_SURROGATE_EXPLORATION_FRACTION = 0.10
```

This is not compatibility with NSGA-II. It is an anti-starvation mechanism for
surrogate-assisted NSGA-III.

If the user rejects exploration quota, document the risk: NSGA-III cannot
recover a branch that the surrogate always predicts as bad.

## Surrogate Fixes To Implement Alongside NSGA-III

The NSGA-III switch should not be treated as sufficient. Implement these in
roughly this priority order.

### Priority 1: Real Historical Error Audit

In `project/surrogate/runtime.py`:

- Stop setting `pred_costs = true_costs`.
- Predict historical/training samples with the current model.
- Disable exact-neighbor snapping for historical error evaluation.
- Calculate per-objective relative errors.
- Store meaningful `mean_relative_error`, and ideally p50/p90/p95 values.

Potential helper:

```python
def _predict_costs_for_error_audit(state, x, *, snap: bool = False):
    ...
```

Important: this may be expensive for thousands of samples. Use batching through
existing `SURROGATE_INR_SAMPLE_BATCH_EVAL` and `SURROGATE_INR_QUERY_BATCH_EVAL`.

### Priority 2: Calibrated Intervals

Current interval width uses:

```python
relative_width = max(config.SURROGATE_ALPHA, state.mean_relative_error)
delta = max(std, abs(value) * relative_width, relative_width)
```

Because `mean_relative_error` is zero today, intervals are dominated by the
fixed `SURROGATE_ALPHA = 0.10` floor. After real error audit, use per-objective
error quantiles.

Recommended interval formula:

```text
delta_j = max(
    ensemble_std_j,
    abs(pred_j) * historical_relative_error_p90_j,
    historical_absolute_error_p90_j,
    SURROGATE_INTERVAL_FLOOR
)
```

Store those calibration values in checkpoint JSON.

### Priority 3: Objective-Aware Loss

Keep full-field rawData training. Add cost-aware terms.

For the current test task, objective metrics are:

```text
obj1 metrics:
  summary[0] toward 0.72
  summary[1] toward 0.28

obj2 metrics:
  curve0 mean in axis range [0.46, 0.54] toward 0.40
  curve1 mean in axis range [0.46, 0.54] toward 0.44

obj3 metric:
  surface mean in center window [0.46, 0.54] x [0.46, 0.54] toward 0.40
```

Do not hard-code this only inside `surrogate/modeling.py` long term. Prefer a
task-owned API in `job_template` if possible, for example:

```python
job_template.api.calculate_objective_metrics_from_raw_data(...)
job_template.api.calculate_objective_costs_from_metrics(...)
```

Short-term acceptable implementation:

- Add differentiable torch versions for the current default test task.
- Keep them near task code or behind `job_template.api`, not buried in generic
  optimizer code.

Loss components:

```text
full_field_loss: all rawData slots
window_loss: cost-relevant rawData windows
objective_metric_loss: loss on pre-cost scalar metrics
objective_cost_loss: loss on tanh-shaped costs
```

Suggested initial weights, inspired by reference:

```text
full_field_loss: 1.0
window_loss: 1.0 to 2.0
objective_metric_loss: 0.15
objective_cost_loss: 0.25
```

Tune after observing A/B prediction errors.

### Priority 4: Relative Loss Where It Matters

Use relative loss on objective costs and possibly objective metrics:

```text
abs(pred - true) / max(abs(true), eps)
```

Suggested eps:

```text
SURROGATE_COST_RELATIVE_EPS = 0.03 or 0.05
SURROGATE_METRIC_RELATIVE_EPS = task-dependent
```

Avoid making rawData full-field loss purely relative unless a floor prevents
near-zero background domination.

### Priority 5: Exact-Neighbor Snapping

`SURROGATE_EXACT_NEIGHBOR_RADIUS = 0.08` can hide model error near known
training samples. It may be useful for prediction, but do not use it for error
audit. Consider lowering the default or making it only apply when the distance
is extremely small.

## Tests To Add Or Update

### Optimizer NSGA-III Tests

Update tests expecting `pymoo.NSGA2` diagnostics to expect `pymoo.NSGA3`.

Add tests that:

1. Multi-objective optimizer diagnostics include NSGA-III reference direction
   count.
2. `run_one_generation()` still returns the requested population size or the
   documented NSGA-III size behavior.
3. Surrogate alpha selection uses pooled survival rather than pairwise
   replacement.
4. No import path still depends on `pymoo.algorithms.moo.nsga2`.

### Surrogate Error Tests

Add a test where surrogate prediction is intentionally imperfect and verify:

```text
evaluate_historical_errors() is not all zeros
checkpoint mean_relative_error is not zero
interval width increases with historical error
```

### A/B Branch Regression Test

Create a lightweight test that does not train the full surrogate for 40 minutes.
Use monkeypatched surrogate predictions:

- Candidate A has true good costs but surrogate-predicted bad costs.
- Candidate B has predicted good costs.
- Verify that an exploration quota or NSGA-III pooled survival keeps at least
  some non-B candidates.

This test should focus on selection logic, not full INR training.

### In-Memory Baseline Diagnostic Script

Consider adding a non-default diagnostic script under `project/test/` or
`project/tools/test/` that evaluates `test_com` in memory without writing job
folders. It should not be part of slow default CI unless kept small.

The analysis used this direct chain:

```text
raw variables
-> project.job_template.test_com.evaluate_raw_data()
-> in-memory rawData items with metadata
-> project.job_template.calc_cost.calculate_cost()
```

This is much faster than using `evaluate_manager` job folders.

## Suggested Implementation Sequence

1. Read required docs and inspect current dirty worktree. Do not revert user
   changes.
2. Replace NSGA2 with NSGA3 in `gpsaf_pymoo.py`.
3. Add reference-direction helper and diagnostics.
4. Update tests that refer to NSGA2.
5. Change surrogate alpha selection from pairwise alpha batches to pooled
   NSGA-III survival on predicted costs.
6. Keep or lightly adapt beta phase; if possible, pool anchors + beta candidates
   and run NSGA-III survival again.
7. Add a small exploration quota that bypasses surrogate selection, unless the
   user explicitly rejects it.
8. Fix surrogate historical error audit so it is not zero by construction.
9. Add interval calibration from real historical prediction error.
10. Add objective-aware loss while keeping full-field loss.
11. Run focused tests.
12. Update `dev_doc` architecture/prompt/change record.
13. Move this toDo file to `dev_doc/obsolete/` after the task is complete.

## Risks And Mitigations

### Risk: NSGA-III Alone Does Not Recover A Branch

If surrogate predicts all A-branch candidates as very bad, reference directions
will not rescue them. Mitigation: exploration quota and real error calibration.

### Risk: Reference Direction Count Differs From Population Size

For 3 objectives, `n_partitions=30` gives 496 directions, close to 500. Decide
and document whether the algorithm keeps `pop_size=500` or uses 496.

### Risk: Objective-Aware Loss Becomes Too Task-Specific

The framework is supposed to support arbitrary task templates. Mitigation:
place task-specific objective metric extraction behind `job_template.api`, or
make the surrogate gracefully fall back to full-field loss if no objective-aware
hook is available.

### Risk: Relative Loss Overweights Near-Zero Values

Mitigation: use eps floors and apply relative loss primarily to objective costs
or metrics, not every rawData pixel.

### Risk: Training Time Increases

The user's current full training is about 40 minutes per generation. Objective
loss terms may add overhead. Mitigation:

- Keep cost/metric extraction vectorized.
- Add fast monkeypatched/unit tests.
- Avoid slow full training in default test suite.

## Useful External References

NSGA-III:

```text
Deb and Jain, "An Evolutionary Many-Objective Optimization Algorithm Using
Reference-Point-Based Nondominated Sorting Approach, Part I: Solving Problems
With Box Constraints", IEEE TEC, 2014.
```

pymoo NSGA-III documentation:

```text
https://pymoo.org/algorithms/moo/nsga3.html
```

NSGA-II background:

```text
Deb et al., "A fast and elitist multiobjective genetic algorithm: NSGA-II",
IEEE TEC, 2002.
```

GPSAF:

```text
GPSAF: A Generalized Probabilistic Surrogate-Assisted Framework for Constrained
Single- and Multi-objective Optimization.
```

The repository also contains:

```text
reference/GPSAF A Generalized Probabilistic Surrogate-Assisted Framework for Constrained Single- and Multi-objective Optimization.tex
```

## Final Recommendation

Implement the user's requested full NSGA-III switch, but do not treat it as the
main fix for the observed collapse. The main fix is the combination of:

```text
NSGA-III pooled survival
+ truthful surrogate error calibration
+ objective-aware full-field surrogate training
+ a small anti-starvation exploration quota
```

This should preserve the user's desired full-field surrogate philosophy while
making cost-critical regions and Pareto directions visible enough that the A
branch is not eliminated early.
