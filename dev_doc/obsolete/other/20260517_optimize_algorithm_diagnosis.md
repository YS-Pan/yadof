# 2026-05-17 Optimize Algorithm Diagnosis

## Purpose

This note is written for a follow-up coding agent that will modify `project/optimize`.
It summarizes an investigation into why the current harder `job_template` problem no
longer shows clear generation-by-generation average cost improvement.

The short version:

1. The current optimizer is **not NSGA-III**. In the active code path, multi-objective
   optimization uses `pymoo.NSGA2`.
2. The default config disables surrogate assistance, so the current run is effectively
   baseline NSGA-II-like search, not GPSAF with surrogate pressure.
3. The main suspected bug is in how optimizer state is reconstructed from history:
   the code feeds **all historical samples** into pymoo and then asks for offspring
   without first reducing the archive to the current survivor population. This weakens
   or destroys generation-to-generation selection pressure.
4. The current harder synthetic task is genuinely much harder, but not so hard that a
   correct evolutionary loop should be flat. A standard continuous NSGA-II loop on the
   same in-memory objective shows clear improvement.

No code was changed during this investigation.

## Files Read For Context

The analysis was based on full reads of:

- `architecture/*.md`
- `prompt/*.md`
- `prompt/10_modules/*.md`
- `reference_map.md`
- `spec 20260502.md`
- `reference/20260403 fanyufei/prompt/**/*.md`

Important implementation files inspected:

- `project/config.py`
- `project/optimize/api.py`
- `project/optimize/gpsaf.py`
- `project/optimize/gpsaf_pymoo.py`
- `project/optimize/gpsaf_phases.py`
- `project/optimize/gpsaf_misc.py`
- `project/job_template/parameters_constraints.py`
- `project/job_template/test_com.py`
- `project/job_template/calc_cost.py`
- `project/evaluate_manager/*.py`
- `project/recorded_data/*.py`
- `reference/20260403 fanyufei/code/optimize.py`
- `reference/20260403 fanyufei/code/optimize_misc.py`
- `reference/20260403 fanyufei/code/optConfig.py`

## Current Optimizer Reality

### It Is Not Currently NSGA-III

The current v3 docs already say this, and the code confirms it:

- `project/optimize/gpsaf_pymoo.py` imports and uses:
  - `pymoo.algorithms.soo.nonconvex.ga.GA` for one objective.
  - `pymoo.algorithms.moo.nsga2.NSGA2` for multiple objectives.
- The branch is in `_make_algorithm()`:
  - if `objective_count <= 1`: return `GA(...)`
  - else: return `NSGA2(...)`

Relevant locations:

- `project/optimize/gpsaf_pymoo.py`, around lines 90-106.
- `project/optimize/gpsaf_pymoo.py`, diagnostics reports `baseline_optimizer="pymoo.NSGA2"` for 3 objectives.

The old project did use DEAP NSGA-III:

- `reference/20260403 fanyufei/code/optimize.py` computes reference points via
  `tools.uniform_reference_points(nobj, p)`.
- `reference/20260403 fanyufei/code/optimize_misc.py` registers
  `tools.selNSGA3`.
- Old config:
  - `EXPECT_POP_SIZE = 146`
  - `P_CAP = 400`
  - `CXPB = 1.0`
  - `MUTPB = 1.0`
  - `DIM_MUT_PER_INDV = 6`
  - `ETA_CX = 10`
  - `ETA_MUT = 10`

Therefore, do not spend time tuning NSGA-III reference point parameters in the current
code unless the task is explicitly to restore NSGA-III or add it as an option.

### Surrogate/GPSAF Assistance Is Disabled By Default

`project/config.py` currently has:

```python
OPTIMIZE_SURROGATE_ALPHA = 1
OPTIMIZE_SURROGATE_BETA = 0
OPTIMIZE_SURROGATE_GAMMA = 0.5
```

`project/optimize/gpsaf.py` uses:

```python
def _surrogate_requested() -> bool:
    alpha = int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1))
    beta = int(getattr(config, "OPTIMIZE_SURROGATE_BETA", 0))
    return alpha > 1 or beta > 0
```

With alpha 1 and beta 0, no surrogate training or prediction is used. The recorded
optimization metadata also reports:

```text
surrogate_mode = disabled_by_gpsaf_parameters
baseline_optimizer = pymoo.NSGA2
```

This matters because the user may expect "GPSAF" behavior, but the active default is
really a baseline NSGA-II-like loop inside the GPSAF-shaped wrapper.

## Main Suspected Bug: Archive Rebuild Does Not Reduce To Survivors Before Ask

### Current Flow

Each generation call is stateless at the Python object level:

1. `run_generations()` calls `run_one_generation()` repeatedly.
2. Each `run_one_generation()` reloads all completed records through
   `history_records()`.
3. `baseline_records()` calls `history_population(context, history)`.
4. `history_population()` creates a new pymoo algorithm and calls `algorithm.tell(...)`
   with all historical samples.
5. For `generation_index > 0`, `baseline_records()` immediately calls
   `generate_candidate_pool(context, state, ...)`.
6. `generate_candidate_pool()` calls `state.ask()`.

Relevant locations:

- `project/optimize/api.py`, `run_generations()`.
- `project/optimize/gpsaf.py`, `run_one_generation()`.
- `project/optimize/gpsaf_pymoo.py`, `history_population()`.
- `project/optimize/gpsaf_pymoo.py`, `baseline_records()`.
- `project/optimize/gpsaf_pymoo.py`, `generate_candidate_pool()`.

### Why This Is A Problem

`history_population()` does not reduce `algorithm.pop` to `population_size`.
It leaves `algorithm.pop` as the full archive after a single `tell()`.

A quick inspection on the current recorded data confirmed this:

```text
history rows fed to history_population: 1000
configured pop_size: 500
len(state.pop): 1000
len(state.opt): 24
state.n_gen: 2
```

That means the next call to `state.ask()` can select parents from a full archive of
old and new records, rather than from the selected survivor population. The effect is
that many new offspring look close to random archive recombinations, and the average
cost of the newly evaluated generation stays close to the random baseline.

This matches the user's observation: the average cost of newly evaluated individuals
is nearly horizontal even though the archive contains better individuals.

### Evidence From Current Recorded Data

Current `recorded_data` contained 1601 completed rows and 1 error row:

```text
generation 0: 500 completed
generation 1: 500 completed
generation 2: 497 completed, 1 error
generation 3: 104 completed
```

Per-generation evaluated batch statistics:

```text
gen 0: n=500, mean(sum costs)=2.115758, min(sum costs)=0.958703
gen 1: n=500, mean(sum costs)=2.091627, min(sum costs)=0.789137
gen 2: n=497, mean(sum costs)=2.052859, min(sum costs)=1.034864
gen 3: n=104, mean(sum costs)=2.068080, min(sum costs)=0.923034
```

This looks almost flat.

But if one reconstructs the survivor population from all history through each
generation, there is real improvement in the selected archive:

```text
through gen 0: history=500,  survivor mean(sum)=2.115758, min=0.958703
through gen 1: history=1000, survivor mean(sum)=1.850233, min=0.789137
through gen 2: history=1497, survivor mean(sum)=1.721177, min=0.789137
through gen 3: history=1601, survivor mean(sum)=1.698428, min=0.789137
```

So the optimizer has discovered better samples, but the next evaluated batch is not
being generated with enough pressure from the survivor population.

### In-Memory Reproduction

The same current `job_template` objective was evaluated in memory, bypassing job
folders and `recorded_data`.

When using the current `baseline_records()` style, with full-history state rebuild:

```text
gen 0 batch mean(sum)=2.115758, min=0.958703
gen 1 batch mean(sum)=2.091627, min=0.789137
gen 2 batch mean(sum)=2.053159, min=1.034864
gen 3 batch mean(sum)=2.062885, min=1.031930
gen 4 batch mean(sum)=2.059458, min=0.826119
gen 5 batch mean(sum)=2.022970, min=0.834597
gen 6 batch mean(sum)=2.047372, min=0.652077
gen 7 batch mean(sum)=2.014988, min=0.814119
gen 8 batch mean(sum)=2.054932, min=0.609089
gen 9 batch mean(sum)=2.052798, min=0.799583
```

When changing only the reconstruction behavior so the historical archive is reduced
to survivors before `ask()`:

```text
gen 0 batch mean(sum)=2.115758, min=0.958703
gen 1 batch mean(sum)=2.091627, min=0.789137
gen 2 batch mean(sum)=1.925256, min=0.836499
gen 3 batch mean(sum)=1.789765, min=0.631968
gen 4 batch mean(sum)=1.699515, min=0.629339
gen 5 batch mean(sum)=1.597843, min=0.692480
gen 6 batch mean(sum)=1.555855, min=0.648884
gen 7 batch mean(sum)=1.482290, min=0.650868
gen 8 batch mean(sum)=1.438323, min=0.497780
gen 9 batch mean(sum)=1.367161, min=0.520315
```

When running a standard continuous pymoo NSGA-II ask/tell loop on the same in-memory
objective:

```text
gen 0 offspring mean(sum)=2.115758, pop mean(sum)=2.115758
gen 1 offspring mean(sum)=2.075879, pop mean(sum)=1.839973
gen 2 offspring mean(sum)=1.912439, pop mean(sum)=1.673148
gen 3 offspring mean(sum)=1.759511, pop mean(sum)=1.525618
gen 4 offspring mean(sum)=1.688678, pop mean(sum)=1.406100
gen 5 offspring mean(sum)=1.579946, pop mean(sum)=1.338146
gen 6 offspring mean(sum)=1.508783, pop mean(sum)=1.243834
gen 7 offspring mean(sum)=1.463306, pop mean(sum)=1.214467
gen 8 offspring mean(sum)=1.391370, pop mean(sum)=1.153483
gen 9 offspring mean(sum)=1.379713, pop mean(sum)=1.112834
```

This strongly suggests the objective is optimizable and the flat line is mainly an
optimizer-state handling issue.

## Recommended First Code Change

In `project/optimize/gpsaf_pymoo.py`, modify the history-to-pymoo reconstruction path
so a new generation uses a selected survivor population as the algorithm's active
population before calling `ask()`.

The current function:

```python
def history_population(context: PymooContext, history: Sequence[HistoryRecord]):
    algorithm = new_algorithm(context)
    rows = [record for record in history if record.x]
    if rows:
        algorithm.tell(
            infills=Population.new(
                X=_x_matrix([record.x for record in rows], context.problem.variable_count),
                F=_fitness_matrix([record.costs for record in rows], context.problem.objective_count),
            )
        )
    return algorithm
```

Possible approach:

1. Keep a full archive for diagnostics if desired.
2. After `history_population(...)`, call `_selected_population(context, state, size)`.
3. Assign the selected population back to `state.pop` before `generate_candidate_pool(...)`.
4. Consider also setting `state.opt` consistently if pymoo expects it.

Sketch only, not tested as final code:

```python
def survivor_state_from_history(context, history, size):
    state = history_population(context, history)
    selected = _selected_population(context, state, size)
    if len(selected) > 0:
        state.pop = selected
        # Optional: inspect pymoo's expectations for opt.
        # state.opt = selected
    return state
```

Then in `baseline_records()` for `generation_index > 0`, use that survivor state
before calling `generate_candidate_pool()`.

Also inspect the surrogate path:

- `project/optimize/gpsaf_phases.py`, `surrogate_population()` calls
  `base_state = history_population(context, history)`.
- `run_alpha_phase()` and `run_beta_phase()` call `generate_candidate_pool()` from
  that state.

The same archive-vs-survivor issue probably affects surrogate alpha/beta phases too.
If a helper is introduced, use it consistently in both baseline and surrogate paths.

## Recommended Tests

Add tests that would fail under the current behavior.

### Test 1: `history_population` Archive Size Is Not Used As Mating Population

Create a mocked history larger than `population_size`, e.g. 20 rows with pop size 5.
After the reconstruction helper, assert:

```python
len(state.pop) == 5
```

Current behavior leaves `len(state.pop) == len(history)`.

### Test 2: Offspring Mean Improves On A Simple Objective

Use a cheap deterministic objective such as:

```python
f1 = x0
f2 = x1
```

or a single-objective sphere with `variable_count=2`.
Run several generations through `run_generations()` with mocked evaluation and
recorded history. Assert a meaningful trend in the generated population or survivor
population.

Be careful: for true multi-objective objectives, average sum is not the formal
optimization target, so the test should be conservative.

### Test 3: Surrogate Path Uses Survivor State

When `OPTIMIZE_SURROGATE_ALPHA > 1` or `OPTIMIZE_SURROGATE_BETA > 0`, verify that
candidate generation does not use the full historical archive as the mating
population.

## Secondary Issue: Mutation Settings Are Much Weaker Than Old Project

Old project config:

```python
CXPB = 1.0
MUTPB = 1.0
DIM_MUT_PER_INDV = 6
ETA_CX = 10
ETA_MUT = 10
```

Current v3 config:

```python
OPTIMIZE_CROSSOVER_PROBABILITY = 0.80
OPTIMIZE_MUTATION_PROBABILITY = 0.35
OPTIMIZE_CROSSOVER_ETA = 20.0
OPTIMIZE_MUTATION_ETA = 20.0
OPTIMIZE_DIM_MUT_PER_INDIVIDUAL = 1.0
```

In `project/optimize/gpsaf_pymoo.py`, mutation is:

```python
PM(
    prob=OPTIMIZE_MUTATION_PROBABILITY,
    prob_var=OPTIMIZE_DIM_MUT_PER_INDIVIDUAL / dim,
    eta=OPTIMIZE_MUTATION_ETA,
    at_least_once=True,
)
```

For 20 dimensions, `prob_var = 1 / 20 = 0.05`, with mutation applied to only about
35% of offspring. This is far weaker than the old setup, where every offspring was
mutated and roughly 6 dimensions per individual were mutation candidates.

Recommendation:

1. Fix the survivor-state issue first.
2. Then tune mutation if convergence is still too slow.
3. Reasonable next experiment after the fix:
   - `OPTIMIZE_MUTATION_PROBABILITY = 1.0`
   - `OPTIMIZE_DIM_MUT_PER_INDIVIDUAL = 3.0` to `6.0`
   - `OPTIMIZE_CROSSOVER_ETA = 10.0`
   - `OPTIMIZE_MUTATION_ETA = 10.0`

Do not tune these first; they may mask the state handling bug.

## Current Problem Hardness

The new default synthetic task is substantially harder than the old one:

- `project/job_template/parameters_constraints.py`: 20 variables, all in `[0, 1]`.
- `project/job_template/test_com.py`:
  - `INPUT_DIM = 20`
  - `LATENT_DIM = 160`
  - nonlinear random projection through sigmoid latent features.
  - curve outputs with localized peaks/valleys.
  - surface output with localized center behavior.
- `project/job_template/calc_cost.py`:
  - only observes narrow windows:
    - curve axis range `(0.46, 0.54)`
    - surface axis ranges `(0.46, 0.54)` and `(0.46, 0.54)`
  - applies tanh-shaped bounded costs.

Random sampling sanity check on 20,000 points:

```text
mean objectives: [0.479012, 0.762916, 0.865084]
mean combined sum: 2.107011
min objectives over all samples: [0.002118, 0.006436, 0.0]
min combined sum: 0.370510
P(combined sum < 1.0): 0.00315
P(all objectives < 0.5): 0.0012
P(obj0 < 0.2): 0.16225
P(obj1 < 0.2): 0.01525
P(obj2 < 0.2): 0.00535
```

So the first generation can easily look bad. However, a correct evolutionary loop
should still improve the survivor population and, usually, the average quality of
new offspring.

## Metrics Warning

The user has been watching "average cost" per evaluated generation. This is useful
for debugging but is not the native objective of NSGA-II/NSGA-III.

For multi-objective minimization, better diagnostics would include:

1. Per-generation evaluated batch mean combined cost.
2. Per-generation best combined cost.
3. Reconstructed survivor population mean combined cost.
4. Number of nondominated points.
5. Hypervolume or an approximate hypervolume if a stable reference point exists.
6. Per-objective min and quantiles.

The current data showed a flat evaluated-batch mean but improving reconstructed
survivors. That distinction is important.

## NSGA-III Notes

The user's memory about NSGA-III hyperparameters is valid for the old project but not
the active code path.

Old project behavior:

- Used DEAP `tools.uniform_reference_points(nobj, p)`.
- Used `tools.selNSGA3`.
- Chose population size through a combinatorial function:

```python
h = lambda p: comb(m + p - 1, p)
```

For 3 objectives and expected population around 146, the exact NSGA-III reference
point count matters. For 3 objectives:

```text
p=15 gives C(17,15)=136 reference points
p=16 gives C(18,16)=153 reference points
```

The old `population_size()` picked whichever count is closer to `EXPECT_POP_SIZE`.

If follow-up work restores NSGA-III in v3, decide explicitly:

1. Add `pymoo.algorithms.moo.nsga3.NSGA3`, not DEAP, unless there is a strong reason
   to reintroduce DEAP.
2. Add config for reference direction generation, e.g. `OPTIMIZE_NSGA3_PARTITIONS`
   or an expected-size-to-ref-dir helper.
3. Set `pop_size` consistently with `len(ref_dirs)`, unless deliberately overriding.
4. Preserve v3 boundaries: problem shape still comes from `job_template.api`, history
   still comes from `recorded_data.api`.

However, the first fix should be the state reconstruction issue, because NSGA-III
would suffer a similar problem if it used the full archive as the active mating
population.

## GPSAF Paper Notes

The local reference paper is:

`reference/GPSAF A Generalized Probabilistic Surrogate-Assisted Framework for Constrained Single- and Multi-objective Optimization.tex`

Relevant conceptual points from the paper:

- GPSAF wraps a baseline population-based algorithm with `infill` and `advance`.
- `alpha=1` disables surrogate tournament pressure.
- `beta=0` disables simulated surrogate iterations.
- `gamma=0.5` was used in experiments.
- The paper used `alpha=30`, `beta=5`, `gamma=0.5` for many experiments.
- It emphasizes using the baseline algorithm's search pattern, not replacing the
  optimizer entirely.

The current v3 implementation has a GPSAF-shaped alpha/beta structure, but with
default `alpha=1`, `beta=0`, it deliberately falls back to baseline search.

## External Documentation Checked

Useful docs for follow-up implementation:

- pymoo NSGA-II:
  `https://pymoo.org/algorithms/moo/nsga2.html`
- pymoo NSGA-III:
  `https://pymoo.org/algorithms/moo/nsga3.html`
- DEAP selection tools:
  `https://deap.readthedocs.io/en/master/api/tools.html#deap.tools.selNSGA3`

Use official pymoo/DEAP docs if implementing algorithm changes.

## Suggested Implementation Order

1. Add a helper that reconstructs a pymoo algorithm from history and reduces its
   active population to survivors of size `population_size`.
2. Use that helper in:
   - baseline generation path in `baseline_records()`.
   - surrogate `alpha` and `beta` starting state in `gpsaf_phases.py`.
3. Add unit tests for archive larger than population size.
4. Run a small in-memory or monkeypatched objective test to confirm generational
   improvement.
5. Run real local `run_generations(3-5, population_size=100 or 500)` and compare:
   - evaluated batch mean,
   - reconstructed survivor mean,
   - best combined cost.
6. Only then tune mutation/crossover.
7. Only then consider restoring NSGA-III as an option.

## Important Caveats

- Do not persist cost files. v3 requires cost to remain dynamically derived from
  rawData through `job_template/calc_cost.py`.
- Do not make `optimize` normalize historical variables itself. Continue to rely on
  `recorded_data.api`.
- Be careful with failed rows. Default history should use completed records only.
- If adding diagnostics, keep optimization metadata lightweight; do not store full
  populations or cost matrices in `optMeta`.
- If the user changes task semantics substantially, historical rawData may become
  misleading. This is already documented as a user responsibility in the spec.

