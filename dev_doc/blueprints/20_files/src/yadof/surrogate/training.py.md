# Blueprint: `surrogate/training.py`

## Contract

Own backend-neutral explicit surrogate values without importing Torch.
`SurrogateTrainingData` accepts only fully materialized normalized rows and complete
structured rawData, owns immutable copies, validates finite real main targets, and
separates a domain-versioned semantic content digest from JSON-safe provenance.
`materialize_training_data()` strictly joins Stage 2 evidence and cost rows by
identity; it never records or silently substitutes a failed row.

`TrainingHandle` owns one non-daemon fit thread, cached terminal result/failure,
wait timeout, cooperative cancellation, context-manager cleanup, and optional exact
generation-snapshot registration. Close releases the runner, training input,
thread, and snapshot lease. `SurrogatePrediction` owns complete immutable transient
rawData, current-snapshot finite costs, exact zero-width intervals, semantic
signatures, and bounded diagnostics; it is never evidence or a posterior draw.
`DeterministicPredictionProvider` is the lightweight runtime-checkable consumer edge
for components that can produce that exact DTO for a candidate-selection pool. It
contains no Torch type and replaces method-name probing for the migrated PCA/SVD
path.
