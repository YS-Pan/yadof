# 2026-07-04 14:47 - Surrogate Query Minibatches

## Context
- Antenna rawData can include full far-field matrices with frequency, theta, and phi axes.
- The existing conditional-INR training loop backpropagated through every flattened rawData query point in every batch. This was acceptable for one-dimensional S-parameter data but became very slow on CPU-only machines for antenna rawData.

## Change
- Added `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` to cap the number of rawData query points used per training step.
- Updated `project/surrogate/modeling.py` to draw stochastic query minibatches when the flattened rawData query count exceeds that cap.
- Reused task-owned rawData importance weights as query sampling probabilities, so objective-relevant windows remain emphasized without multiplying the same weights twice.
- Kept model architecture, ensemble size, epochs, full rawData reconstruction, full prediction query table, and historical error audit behavior intact.
- Updated tests and documentation for the new training behavior, and refreshed the stale default job-template shape assertion to match the current antenna task.

## Rationale
- Stochastic query minibatching reduces CPU backpropagation work for large two- and three-dimensional rawData fields while still training against the full rawData domain over repeated batches and epochs.
- Preserving full prediction and rawData reconstruction avoids changing the public `variables -> rawData -> cost` surrogate contract.

## Impact
- Large antenna far-field training should be substantially faster on machines without GPUs.
- Checkpoint train history now records `query_count`, `train_query_count_per_step`, and whether query subsampling was active.
- Users can raise `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` if they want training to approach or match full-query backpropagation for a small dataset.

## Follow-Up
- If future antenna datasets become much larger, consider streaming or memory-mapped target matrices so flattening itself does not become the next bottleneck.