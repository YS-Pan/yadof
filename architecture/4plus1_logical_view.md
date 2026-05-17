# 4+1 Logical View

## Core Concepts
- Optimization variable: normalized in `optimize`, raw/unnormalized in `recorded_data`.
- rawData: one or more `.npz` files produced by a workflow.
- Cost: dynamic objective value calculated from rawData by current `job_template/calc_cost.py`. The default test task returns three minimization costs in `[0, 1]`.
- Job: one real evaluation sandbox created by `evaluate_manager`.
- Checkpoint: recoverable surrogate state. Surrogate checkpoints include a JSON summary plus conditional-INR member artifacts; optimizer generation metadata is recorded under `recorded_data/optMeta/` and is not treated as a checkpoint.

## Logical Modules
- `optimize`: asks for candidate evaluations and optional surrogate predictions.
- `evaluate_manager`: turns candidate rows into job execution and records results.
- `job_template`: defines the current task and interprets rawData.
- `recorded_data`: stores real raw evidence and serves derived historical views.
- `surrogate`: trains a conditional INR deep ensemble over rawData slots, predicts rawData, and converts it to cost through the same cost path.

## Boundary Rules
- Internal files may call another core module only through that module's `api.py`.
- Internal files should not call their own `api.py` just to reach another module.
- `config.py` is an allowed direct dependency for shared settings.
- `tools` and `test` have looser access rules but should not become runtime dependencies.

## Derived Data Rules
- Stored: job name, raw variables, archived rawData, rawData metadata, job metadata, status, and optimization-level metadata.
- Derived on demand: normalized variables, cost, surrogate errors, Pareto summaries.
- Not stored as source truth: `cost.json`, normalized historical variables, surrogate prediction results.

## Logical Invariants
- `workflow.py` never computes final cost.
- `recorded_data` never trusts old saved cost when returning history.
- `surrogate` never bypasses rawData by learning only `variables -> cost`.
- `surrogate` may learn normalized/scaled rawData internals, but public predictions are reconstructed rawData passed to `job_template.api` for cost.
- Failed records can exist and be inspected, but default optimization history uses completed records.
- Default cost shaping follows the old fanyufei tanh-style soft objective mapping: goal-like values approach 0 and worst-threshold values approach 1.
