# 4+1 Logical View

## Core Concepts
- Optimization variable: normalized in `optimize`, raw/unnormalized in `recorded_data`.
- rawData: one or more `.npz` files produced by a workflow.
- Cost: dynamic objective value calculated from rawData by current `job_template/calc_cost.py`. Objective names, count, physical meaning, and numeric scale are task-specific.
- Job: one real evaluation sandbox created by `evaluate_manager`.
- Individual metadata: job-local lifecycle JSON written by `workflow.py`, including the evaluation start/end times when the workflow reaches those points.
- Checkpoint: recoverable surrogate state. Surrogate checkpoints include a JSON summary plus conditional-INR member artifacts; optimizer generation metadata is recorded under `recorded_data/optMeta/` and is not treated as a checkpoint.

## Logical Modules
- `optimize`: uses GA for single-objective runs and NSGA-III reference-direction survival for multi-objective candidate generation, real evaluations, and optional surrogate-predicted candidate screening.
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
- Stored: job name, raw variables once per individual, archived rawData, compact rawData metadata, workflow-owned `started_at`/`ended_at`, run/generation identifiers, job metadata, status, and optimization-level metadata.
- Derived on demand: normalized variables, cost, surrogate errors, Pareto summaries.
- Not stored as source truth: `cost.json`, normalized historical variables, repeated variable payloads inside every rawData metadata item, surrogate prediction results, and submit-side `created_at`.

## Logical Invariants
- `workflow.py` never computes final cost.
- `recorded_data` never trusts old saved cost when returning history.
- `surrogate` never bypasses rawData by learning only `variables -> cost`.
- `surrogate` may learn normalized/scaled rawData internals, but public predictions are reconstructed rawData passed to `job_template.api` for cost.
- `surrogate` historical error audits must use real model predictions rather than substituting true historical costs.
- Exact-neighbor snapping or near-training-sample replacement is not part of the current surrogate contract and must not be added unless explicitly requested by the user.
- Task-owned rawData importance weights may emphasize objective-relevant windows, but surrogate training must still retain full-field rawData coverage. For very large rawData fields, stochastic query minibatches may limit per-step backpropagation work while resampling from the full query table and leaving full-field prediction/reconstruction intact.
- Current HFSS far-field rawData is stored as full-matrix data by default; objective cost calculation may select phi/theta/frequency windows from that matrix, but it must not make the workflow export only those windows unless a task intentionally requests trace diagnostics.
- Failed records can exist and be inspected, but default optimization history uses completed records.
- `evaluate_manager` may add runner diagnostics, but workflow-owned timing is read from the job folder before recording.
- Current HFSS cost shaping follows the old huangzetao/fanyufei tanh-style soft objective mapping: goal-like values approach 0 and worst-threshold values approach 1.
