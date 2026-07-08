# Module blueprint: optimize

## Intent
- Own the optimizer-facing API and the GPSAF-style search policy, using NSGA-III for multi-objective diversity while staying independent from workflow, simulator, job execution, and rawData storage details.
- Work in normalized variable space and treat historical samples as advisory state supplied by `recorded_data`.
- Support warm-started runs, optional surrogate assistance, and small optimization-level generation metadata.

## Functionalities
- `api.run_one_generation()` delegates one generation to `gpsaf.run_one_generation()`.
- `api.run_generations()` wraps repeated generation execution, assigns a run id and optimization index, and records lightweight generation metadata through `recorded_data.api`.
- `gpsaf.py` resolves problem width/objective width, builds a pymoo-backed context, chooses baseline or surrogate-assisted candidate generation from the latest already-trained surrogate state, evaluates the chosen population, and schedules new surrogate training after real jobs have been submitted.
- `gpsaf_pymoo.py` adapts GA/NSGA-III ask-tell behavior to the unit hypercube, chooses Das-Dennis reference directions near the requested population size, exposes NSGA-III survival for candidate pools, and reconstructs optimizer state from historical records.
- `gpsaf_phases.py` implements surrogate alpha/beta pooled NSGA-III candidate phases, an exploration quota that bypasses surrogate selection, uncertainty diagnostics, and graceful fallback when surrogate calls fail.
- `gpsaf_misc.py` imports public APIs dynamically, reads historical optimization results, calls `evaluate_manager.api` with run/generation context, and keeps cost comparison helpers small.
- `problem_info.py` derives variable count, objective count, and objective names from `job_template.api`.
- The optimizer selects single-objective or multi-objective behavior from the objective count reported by the active `job_template`.

## I/O Format
- Input population rows are normalized floats in `[0, 1]`.
- Historical rows are `(job_name, normalized_variables, costs)` from `recorded_data.api`.
- Evaluation requests go to `evaluate_manager.api.evaluate_generation/evaluate_population/evaluate` with `run_id`, `optimization_index`, and `generation_index` when available.
- Public result is `OptimizationResult(generation_index, population, costs, history_count, source, surrogate_used, diagnostics)`.
- Optimizer generation metadata should remain lightweight and live under `recorded_data/optMeta/`; durable real-evaluation data belongs to `recorded_data`.

## Non-Obvious Techniques
- `optimize` must not read `job_template` directly to normalize historical variables; only problem shape metadata may come from `job_template.api`.
- If no history exists, candidate generation starts from pymoo random sampling in the unit box.
- If history exists and surrogate assistance is disabled, the baseline optimizer still uses history to seed candidate generation.
- If surrogate assistance is requested but unavailable, the optimizer records diagnostics and falls back to baseline candidates.
- Individual evaluation records receive the same `optimization_index` and `generation_index` that optimizer generation metadata uses, so individual history can be grouped without reconstructing context from job names.
- Multi-objective behavior is selected from the current objective count: GA for one objective, NSGA-III for multiple objectives. NSGA-II compatibility is intentionally removed from the optimizer path.
- Surrogate alpha selection predicts `alpha * population_size` candidates as one pool and applies NSGA-III survival instead of position-wise pairwise replacement.
- Surrogate beta selection pools anchors with beta-generated predicted candidates and applies NSGA-III survival again.
- `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` reserves a small number of real-evaluation candidates from baseline offspring/random refill so a branch is not eliminated solely by a biased surrogate.

- Staggered surrogate scheduling avoids the old double-train pattern. A generation uses the latest completed surrogate state for GPSAF candidate screening, submits real jobs, and then starts training for the just-submitted generation.
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` bounds staleness. With the default value `2`, the optimizer allows one- and two-generation lag but blocks before submitting work that would use a three-generation-old model.

## Mutability Profile
- GPSAF policy, NSGA-III reference-direction controls, pymoo operator parameters, and surrogate alpha/beta/exploration behavior are expected to evolve.
- API shapes should stay stable because tests, future launchers, and architecture docs depend on them.
- This module should not absorb simulator, workflow, or recording behavior when adding features.
