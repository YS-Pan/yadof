# Module blueprint: surrogate

## Intent
- Provide optimizer-facing surrogate prediction while preserving the required `normalized variables -> rawData -> cost` chain.
- Train only from real records stored in `recorded_data`.
- Estimate uncertainty from the minimum and maximum objective costs predicted by deep-ensemble members without introducing a separate durable surrogate-result archive.

## Functionalities
- `api.py` exports training, prediction, historical-error, and staggered-training scheduling functions: `train()`, `predict_population()`, `evaluate_historical_errors()`, `start_training()`, `wait_for_pending_training()`, `ensure_fresh_enough()`, `has_trained_state()`, and `latest_state_generation()`.
- `runtime.py` loads training data from `recorded_data.api`, validates and flattens rawData numeric arrays, asks `job_template.api` for task-owned rawData importance weights when available, builds query coordinates and field ids, scales targets, calls the INR trainer, reconstructs predicted rawData, audits historical prediction error, writes checkpoints through `checkpoints.py`, records training metadata through `metadata.py`, and caches the latest state in memory.
- `modeling.py` defines the PyTorch conditional INR deep ensemble, including Fourier coordinate features, field embeddings, importance-weighted stochastic query minibatches for large rawData fields, weighted full-field and relative losses, bootstrap/mixup member training, artifact saving, and member-level prediction.
- `scheduler.py` owns the staggered training lifecycle: background one-at-a-time training after real jobs are submitted, pending-training waits, and maximum training-lag enforcement.
- `checkpoints.py`, `metadata.py`, and `types.py` hold checkpoint persistence, recorded surrogate training metadata, and shared surrogate dataclasses/type aliases so `runtime.py` stays focused on model data flow.
- `predict_raw_data()` reconstructs rawData items from predicted flattened arrays.
- `predict_population()` converts predicted rawData to costs through `job_template.api` and returns both costs and cost intervals.
- `evaluate_historical_errors()` returns the train-time relative-error audit used by optimizer-side diagnostics. The audit uses model predictions and must not substitute true historical costs.
- Prediction intervals are the per-objective minimum and maximum costs across deep-ensemble member predictions. They do not use historical error quantiles, fixed floors, or a delta around the mean prediction.

## I/O Format
- Training input: `parameter_names`, `normalized_variables`, and `raw_data` from `recorded_data.api`.
- Model input: normalized population rows.
- RawData prediction output: samples shaped as `samples[sample][rawData_item]`.
- Optimizer prediction output: `(costs, ((lower, upper), ...))` for each individual.
- Checkpoints are `generation_*.json` summaries plus `generation_*_conditional_inr/` artifact folders under `config.SURROGATE_CHECKPOINT_DIR`.
- Checkpoint JSON includes `mean_relative_error`, historical relative-error p50/p90/p95, historical absolute-error p90, full query count, and training query count per step. The auxiliary artifact stores target scaling, query table, training flat values, and query weights.
- INR artifact folders contain `inr_meta.json`, `member_*.pt`, and `model_aux.npz` with query-table, field-id, target-scaling, and training-flat-value payloads.

## Non-Obvious Techniques
- The surrogate skips rawData arrays that are constant across training samples; only varying numeric slots become conditional-INR modeled dimensions.
- Each modeled rawData slot receives a field id and query coordinates. Axes declared in rawData metadata are reused when available, otherwise normalized index coordinates are generated.
- RawData targets are min/range scaled before sigmoid-bounded INR training, then inverse transformed before rawData reconstruction.
- Small training sets disable bootstrap member resampling so the ensemble still sees all available expensive evaluations.
- Mixup between observed designs regularizes interpolation between sparse expensive samples.
- Predicted rawData metadata is marked with `source = project.surrogate.runtime` and `surrogate_prediction = True`, while original variable echoes are removed.
- Exact-neighbor snapping is intentionally absent. Do not reintroduce snapping or near-training-sample replacement unless the user explicitly asks for that feature.
- Relative error uses `SURROGATE_RELATIVE_ERROR_EPS`; INR training also has a relative-loss term with `SURROGATE_INR_RELATIVE_LOSS_EPS` so small-magnitude rawData dimensions receive attention without letting near-zero background dominate.
- Task-specific objective windows should be expressed through `job_template.api.get_rawdata_importance_weights()` where possible. Scalar and 1D rawData slots are always included in each training step, while large 2D/3D fields use weighted stochastic query minibatch sampling; objective windows are still emphasized without backpropagating every far-field point in every batch. The surrogate falls back to uniform query sampling and weights when a task does not provide this hook.
- If no schema/model is available, prediction returns `inf` costs with zero-width intervals rather than pretending to know a value.

- Surrogate prediction does not implicitly train a model. GPSAF either uses the latest already-trained in-memory state or falls back to baseline candidates until the first staggered training pass finishes.
- Training metadata is written to `recorded_data/optMeta/optMeta.jsonl` as `record_type = "surrogate_training"`, separate from real individual records and separate from checkpoint artifacts.

## Mutability Profile
- Model family, uncertainty calculation, and checkpoint payload can evolve.
- The public `api.py` functions and rawData-first output contract should remain stable.
- The surrogate must not start saving optimize-space prediction results as durable evaluation history.
