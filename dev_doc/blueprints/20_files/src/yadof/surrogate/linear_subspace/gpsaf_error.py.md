# File blueprint: PCA/SVD GPSAF error bootstrap

Split explicit materialized training data deterministically into five folds
(leave-one-out below five). Fit independent in-memory deployable models on the
complement and predict held-out rows only. Both truth and predictions pass
`sample.cost_items()` through the current cost chain with assigned parameters.
Return per-objective maximum absolute held-out error. Do not publish checkpoints,
mutate the active fitted state, call real simulators, or write formal history.
