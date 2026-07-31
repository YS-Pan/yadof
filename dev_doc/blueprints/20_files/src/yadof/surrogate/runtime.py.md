# File blueprint: src/yadof/surrogate/runtime.py

## Intent
- Own surrogate training and prediction data flow while preserving `normalized variables -> rawData -> cost`.

## Functionalities
- Load training bundles from `recorded_data.api`.
- Flatten numeric rawData slots into conditional-INR query tables and reconstruct predicted rawData.
- Query one modeled rawData slot at arbitrary physical axis coordinates without
  mutating its checkpoint schema.
- Apply task-owned rawData importance weights only after compatible numeric rawData
  slots have entered the modeled query table; the weights alter full-query loss
  attention or stochastic query-sampling probability, not data inclusion.
- Train the INR ensemble through `modeling.py`.
- Write checkpoints through `checkpoints.py` and training metadata through `metadata.py`.
- Predict rawData/costs using the latest in-memory trained state.

## I/O Format
- `train(generation_index, started_at=None)` returns a `SurrogateState`.
- `predict_population(population)` returns `(costs, intervals)` for each normalized input row.
- `evaluate_historical_errors()` returns relative historical error rows from the latest trained state.
- `predict_rawdata_slot_members_at_coordinates(...)` returns physical member values
  shaped `[member, sample, *query_shape]` for one slot.

## Non-Obvious Techniques
- Prediction must not auto-train. If `_STATE` is absent, prediction raises and optimizer fallback handles it.
- Training metadata is recorded after checkpoint writing so metadata can point at completed artifacts.
- Stored-grid queries reuse the exact legacy coordinate normalization and scaler
  entries. Off-grid queries linearly interpolate target mean/scale, clamp scaler
  extrapolation to endpoint values, and leave the decoder coordinate unclipped.
- Current INR checkpoints encode three rawData coordinate columns. Dimensions
  beyond the third may retain their full stored grid but cannot yet be changed by
  this query API.

## Mutability Profile
- Data-flow details may evolve, but scheduler, checkpoint, metadata, and type responsibilities should stay in their own files.
