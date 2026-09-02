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
Explicit physical failures may carry no rawData and all positive-infinite costs
with `valid_mask=False`. Every valid row remains complete and finite.
`SurrogateContractError` distinguishes fatal implementation faults from an
unavailable learned prediction. Invalid rows never borrow another row's sample.
Freshness delegates to the component's pure latest-generation inspection even
when supplied data is empty: a training-free real oracle can be current without
inventing training samples. No state plus empty data remains skipped-no-data.
Contract errors from that inspection propagate rather than becoming a fallback.
`DeterministicPredictionProvider` is the lightweight runtime-checkable prediction
edge for components that can produce that exact DTO for a candidate-selection
pool. `DeterministicSurrogateComponent` extends it with validation, semantic
identity, explicit training-data materialization, freshness/state queries, and
start/finish training. It contains no Torch type and replaces method-name probing
for PCA/SVD, conditional-INR, and hierarchical-CAE explicit paths.

`SurrogateSelectionFreshness` and
`assess_surrogate_selection_freshness()` compare the component's latest trained
generation with the current generation and configured maximum lag. This operation
is read-only and returns fail-closed diagnostics; it cannot invoke the retained
blocking scheduler freshness adapter.
