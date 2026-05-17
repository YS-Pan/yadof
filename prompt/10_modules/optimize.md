# Module prompt: optimize

## Intent
- Own the optimizer-facing API and the GPSAF-style search policy while staying independent from workflow, simulator, job execution, and rawData storage details.
- Work in normalized variable space and treat historical samples as advisory state supplied by `recorded_data`.
- Support warm-started runs, optional surrogate assistance, and small optimization-level generation metadata.

## Functionalities
- `api.run_one_generation()` delegates one generation to `gpsaf.run_one_generation()`.
- `api.run_generations()` wraps repeated generation execution and records lightweight generation metadata through `recorded_data.api`.
- `gpsaf.py` resolves problem width/objective width, builds a pymoo-backed context, chooses baseline or surrogate-assisted candidate generation, evaluates the chosen population, and optionally notifies surrogate retraining.
- `gpsaf_pymoo.py` adapts GA/NSGA2 ask-tell behavior to the unit hypercube and reconstructs optimizer state from historical records.
- `gpsaf_phases.py` implements surrogate alpha/beta candidate phases, uncertainty-aware comparisons, and graceful fallback when surrogate calls fail.
- `gpsaf_misc.py` imports public APIs dynamically, reads historical optimization results, calls `evaluate_manager.api`, and keeps cost comparison helpers small.
- `problem_info.py` derives variable count, objective count, and objective names from `job_template.api`.
- With the current default `job_template`, the optimizer sees three objectives and therefore uses the multi-objective pymoo path.

## I/O Format
- Input population rows are normalized floats in `[0, 1]`.
- Historical rows are `(job_name, normalized_variables, costs)` from `recorded_data.api`.
- Evaluation requests go to `evaluate_manager.api.evaluate_generation/evaluate_population/evaluate`.
- Public result is `OptimizationResult(generation_index, population, costs, history_count, source, surrogate_used, diagnostics)`.
- Optimizer generation metadata should remain lightweight and live under `recorded_data/optMeta/`; durable real-evaluation data belongs to `recorded_data`.

## Non-Obvious Techniques
- `optimize` must not read `job_template` directly to normalize historical variables; only problem shape metadata may come from `job_template.api`.
- If no history exists, candidate generation starts from pymoo random sampling in the unit box.
- If history exists and surrogate assistance is disabled, the baseline optimizer still uses history to seed candidate generation.
- If surrogate assistance is requested but unavailable, the optimizer records diagnostics and falls back to baseline candidates.
- Multi-objective behavior is selected from the current objective count: GA for one objective, NSGA2 for multiple objectives.

## Mutability Profile
- GPSAF policy, pymoo operator parameters, and surrogate alpha/beta behavior are expected to evolve.
- API shapes should stay stable because tests, future launchers, and architecture docs depend on them.
- This module should not absorb simulator, workflow, or recording behavior when adding features.
