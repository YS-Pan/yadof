# Module blueprint: surrogate

## Intent
- Provide optimizer-facing surrogate prediction while preserving the required `normalized variables -> rawData -> cost` chain.
- Train only from real records stored in `recorded_data`.
- Estimate uncertainty from model-member spread and historical relative error without introducing a separate durable surrogate-result archive.

## Functionalities
- `api.py` exports `train()`, `predict_population()`, and `evaluate_historical_errors()`.
- `runtime.py` loads training data from `recorded_data.api`, validates and flattens rawData numeric arrays, builds query coordinates and field ids, scales targets, calls the INR trainer, reconstructs predicted rawData, writes generation checkpoints, and caches the latest state in memory.
- `modeling.py` defines the PyTorch conditional INR deep ensemble, including Fourier coordinate features, field embeddings, bootstrap/mixup member training, artifact saving, and member-level prediction.
- `predict_raw_data()` reconstructs rawData items from predicted flattened arrays.
- `predict_population()` converts predicted rawData to costs through `job_template.api` and returns both costs and cost intervals.
- `evaluate_historical_errors()` returns the train-time relative-error audit used by optimizer-side noisy comparisons; intervals also use ensemble member cost spread and `SURROGATE_ALPHA`.

## I/O Format
- Training input: `parameter_names`, `normalized_variables`, and `raw_data` from `recorded_data.api`.
- Model input: normalized population rows.
- RawData prediction output: samples shaped as `samples[sample][rawData_item]`.
- Optimizer prediction output: `(costs, ((lower, upper), ...))` for each individual.
- Checkpoints are `generation_*.json` summaries plus `generation_*_conditional_inr/` artifact folders under `config.SURROGATE_CHECKPOINT_DIR`.
- INR artifact folders contain `inr_meta.json`, `member_*.pt`, and `model_aux.npz` with query-table, field-id, target-scaling, and training-flat-value payloads.

## Non-Obvious Techniques
- The surrogate skips rawData arrays that are constant across training samples; only varying numeric slots become conditional-INR modeled dimensions.
- Each modeled rawData slot receives a field id and query coordinates. Axes declared in rawData metadata are reused when available, otherwise normalized index coordinates are generated.
- RawData targets are min/range scaled before sigmoid-bounded INR training, then inverse transformed before rawData reconstruction.
- Small training sets disable bootstrap member resampling so the ensemble still sees all available expensive evaluations.
- Mixup between observed designs regularizes interpolation between sparse expensive samples.
- Predicted rawData metadata is marked with `source = project.surrogate.runtime` and `surrogate_prediction = True`, while original variable echoes are removed.
- Exact-neighbor snapping can replace near-training predictions with the real training rawData flat vector, controlled by `SURROGATE_EXACT_NEIGHBOR_RADIUS`.
- Relative error uses `SURROGATE_RELATIVE_ERROR_EPS`; INR training also has a relative-loss term so small-magnitude rawData dimensions receive attention.
- If no schema/model is available, prediction returns `inf` costs with zero-width intervals rather than pretending to know a value.

## Mutability Profile
- Model family, uncertainty calculation, and checkpoint payload can evolve.
- The public `api.py` functions and rawData-first output contract should remain stable.
- The surrogate must not start saving optimize-space prediction results as durable evaluation history.
