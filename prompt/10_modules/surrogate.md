# Module prompt: surrogate

## Intent
- Provide optimizer-facing surrogate prediction while preserving the required `normalized variables -> rawData -> cost` chain.
- Train only from real records stored in `recorded_data`.
- Estimate uncertainty from model-member spread and historical relative error without introducing a separate durable surrogate-result archive.

## Functionalities
- `api.py` exports `train()`, `predict_population()`, and `evaluate_historical_errors()`.
- `runtime.py` loads training data from `recorded_data.api`, validates and flattens rawData numeric arrays, fits an RBF/IDW ensemble, writes generation checkpoints, and caches the latest state in memory.
- `predict_raw_data()` reconstructs rawData items from predicted flattened arrays.
- `predict_population()` converts predicted rawData to costs through `job_template.api` and returns both costs and cost intervals.
- `evaluate_historical_errors()` returns relative errors between historical true costs and cross-validated surrogate predictions.

## I/O Format
- Training input: `parameter_names`, `normalized_variables`, and `raw_data` from `recorded_data.api`.
- Model input: normalized population rows.
- RawData prediction output: samples shaped as `samples[sample][rawData_item]`.
- Optimizer prediction output: `(costs, ((lower, upper), ...))` for each individual.
- Checkpoints are JSON summaries plus compressed `.npz` model payloads under `config.SURROGATE_CHECKPOINT_DIR`.

## Non-Obvious Techniques
- The surrogate skips rawData arrays that are constant across training samples; only varying numeric slots become modeled dimensions.
- Predicted rawData metadata is marked with `source = project.surrogate.runtime` and `surrogate_prediction = True`, while original variable echoes are removed.
- Exact-neighbor snapping can replace near-training predictions with the real training rawData flat vector, controlled by `SURROGATE_EXACT_NEIGHBOR_RADIUS`.
- Relative error uses `SURROGATE_RELATIVE_ERROR_EPS` so small costs receive appropriate attention.
- If no schema/model is available, prediction returns `inf` costs with zero-width intervals rather than pretending to know a value.

## Mutability Profile
- Model family, uncertainty calculation, and checkpoint payload can evolve.
- The public `api.py` functions and rawData-first output contract should remain stable.
- The surrogate must not start saving optimize-space prediction results as durable evaluation history.
