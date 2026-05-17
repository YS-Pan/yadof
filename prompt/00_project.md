# Prompt: yadot modular optimization framework

## Intent
- Build the v3 `yadot` framework as a modular, recoverable optimization system under `project/`.
- Merge the mature job orchestration and recording ideas from `reference/20260403 fanyufei` with the surrogate-assisted optimization ideas from `reference/20260418 shorten`.
- Keep the central modeling chain as `normalized variables -> rawData -> cost`, where cost is always derived from rawData through the current `job_template/calc_cost.py`.
- Make the framework tolerant of long-running campaigns: failed evaluations, interrupted runs, changed parameter ranges, changed workflows, and later local/distributed execution backends should not force a rewrite of the core optimizer.

## Functionalities
- `project.optimize` owns the optimization loop, GPSAF-style candidate generation, history warm start, and optional surrogate-assisted candidate selection.
- `project.evaluate_manager` converts normalized individuals into job folders, denormalizes variables through `job_template.api`, runs local jobs, records failures, and returns in-memory costs to the optimizer.
- `project.job_template` owns task-specific files: parameter definitions, workflow, rawData contract, simulator stand-ins or adapters, and rawData-to-cost calculation.
- The current default test task exposes three bounded minimization objectives in `[0, 1]`: target match, curve magnitude, and surface reward.
- `project.recorded_data` stores real evaluation records, raw variables, rawData files, rawData metadata, job metadata, and job names; it does not store cost or normalized variables as durable source data.
- `project.surrogate` trains a conditional INR deep ensemble from `recorded_data`, predicts rawData arrays, converts predictions to costs through `job_template.api`, and writes per-generation checkpoints plus member artifacts.
- `project.tools` remains optional and user-launched; core runtime and tests must not depend on it.
- `project.config` holds cross-module settings such as evaluation mode, job path, optimizer population size, GPSAF controls, and surrogate hyperparameters.
- `project.test` verifies the local closed loop, rawData contract, failure isolation, dynamic cost/normalization behavior, surrogate behavior, and tool compatibility.

## I/O Format
- User-edited inputs are primarily `project/config.py` plus the task-specific files in `project/job_template/`: `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, `test_com.py`, and future simulator model/adaptor files.
- Optimizer input and output use normalized float tuples shaped as `population[individual][variable]`.
- Evaluator input is a generation of normalized float tuples; evaluator output is cost tuples shaped as `population[individual][objective_cost]`.
- Job folders contain copied runtime files, `job_input.json`, `metadata.json`, `metaData.json`, and flat `rawData/*.npz` files. Jobs do not contain or save `cost.json`.
- Recorded history is represented by a manifest plus copied rawData files under `project/recorded_data/rawData/<job_name>/`.
- Public cross-core-module calls go through `api.py` files only: `optimize/api.py`, `evaluate_manager/api.py`, `job_template/api.py`, `recorded_data/api.py`, and `surrogate/api.py`.

## Non-Obvious Techniques
- Cost is deliberately not a persisted evaluation artifact. Any module that needs cost asks `recorded_data` or `job_template` to compute it from rawData using the current `calc_cost.py`.
- Normalized historical variables are also derived data. `recorded_data` stores raw variables and uses current `job_template` parameter ranges to calculate normalized variables on demand.
- `job_static_hash` captures copied static job inputs while excluding runtime outputs and per-individual variable payloads. It makes mid-run task changes visible without making every individual unique by hash.
- rawData directories must stay flat. Each `.npz` is one rawData unit and must include schema-versioned metadata.
- `evaluate_manager` isolates per-individual failures. Prepare, run, timeout, and record failures should become metadata and `inf` costs rather than crashing the whole generation.
- `surrogate` predicts rawData first, then derives costs through the same rawData-to-cost path used for real samples. Its INR training uses target scaling, ensemble/member spread, and relative-loss weighting so small objective values still matter.
- GPSAF surrogate pressure is controlled by `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, and `OPTIMIZE_SURROGATE_GAMMA`; default settings keep the entry point available while not forcing surrogate calls.

## Mutability Profile
- `project/job_template/parameters_constraints.py`, `workflow.py`, `calc_cost.py`, `test_com.py`, and simulator model files are intentionally highly mutable between optimization tasks.
- `project/config.py` is mutable at campaign setup time and occasionally during tuning.
- `project/optimize`, `project/evaluate_manager`, `project/recorded_data`, and `project/surrogate` should change more carefully because they define shared contracts.
- Runtime folders such as `project/jobs/`, `project/recorded_data/rawData/`, and checkpoint directories are generated artifacts.
- `prompt/`, `reference_map.md`, and `architecture/` are documentation artifacts. Update them when module responsibilities or contracts change, not for every small implementation tweak.
