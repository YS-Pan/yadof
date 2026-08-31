# Blueprint: `surrogate/linear_subspace/runtime.py`

## Contract

Fit, publish, and recover one strategy/settings/exact-content-specific PCA/SVD
state from caller-supplied `SurrogateTrainingData`; never scan campaign or durable
history implicitly. Sync and async fit share `TrainingHandle`, with cooperative
cancellation before publication and atomic manifest commit as the race boundary.
Recovery verifies training content, settings, strategy, parameter normalization,
rawData schema, and runtime versions while retaining separate bounded provenance.

State-only prediction reconstructs complete structured rawData, passes it through
the caller's exact generation snapshot, and returns `SurrogatePrediction` with
current costs and zero-width intervals. The GPSAF-only facade converts that DTO to
legacy rows. No prediction calls finalization, recording, or history.
