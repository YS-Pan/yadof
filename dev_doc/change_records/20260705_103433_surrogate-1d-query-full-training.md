# 2026-07-05 10:34 - Surrogate 1D Query Full Training

## Context
- The surrogate speed change uses stochastic query minibatches so large rawData fields do not backpropagate every point in every training step.
- The previous sampling pool was all modeled rawData points together. With mixed rawData shapes, this could under-sample small scalar or 1D arrays because large 2D/3D fields dominate the query count.

## Change
- Added an always-include query path for scalar and 1D rawData slots in `project/surrogate/runtime.py` and `project/surrogate/modeling.py`.
- Each training step now includes all scalar/1D rawData query points and samples only from the remaining high-dimensional query pool.
- Extended surrogate training history with `train_query_sampled_count_per_step`, `train_query_always_included_count`, and `train_query_sampleable_count`.
- Updated config and surrogate blueprints to clarify that `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` caps sampled high-dimensional queries, not always-included scalar/1D queries.

## Rationale
- One-dimensional traces usually contain only tens or hundreds of points, so randomly dropping them provides little speed benefit.
- Keeping these small fields fully visible preserves their training signal while retaining the speed benefit of stochastic sampling for large 2D/3D fields.

## Impact
- For the current HFSS-like synthetic rawData, the three S11 traces contribute 15 always-included query points per training step.
- With `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT = 8192`, the current expected per-step training query count becomes `8192 + 15 = 8207` instead of `8192`, while the large far-field arrays remain sampled.
- Full-field prediction, reconstruction, checkpoints, and historical error audits still use the full query table.

## Follow-Up
- If future tasks include very large 1D traces, consider adding a size threshold or task-owned override for always-included query selection.
