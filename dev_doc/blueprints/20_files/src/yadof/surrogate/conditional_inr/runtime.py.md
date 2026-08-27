# File blueprint: src/yadof/surrogate/conditional_inr/runtime.py

## Intent
- Own surrogate training and prediction data flow while preserving `normalized variables -> rawData -> cost`.

## Functionalities
- Load training bundles from `recorded_data.api`.
- Flatten numeric rawData slots into conditional-INR query tables and reconstruct predicted rawData.
- Keep one controlled private selected-member prediction helper that reuses the
  existing model forward and scaler inverse path for the posterior adapter without
  changing the legacy member-major or mean prediction outputs.
- Query one modeled rawData slot at arbitrary physical axis coordinates without
  mutating its checkpoint schema.
- Pass only compatible recorded real rows and their query-table field identities to
  modeling; runtime does not create synthetic targets or task-owned weights.
- Fit a float64 per-query mean/standard-deviation scaler with the configured floor;
  inverse-scale every linear model output back to physical rawData before current
  task cost calculation.
- Train the INR ensemble through `modeling.py`.
- Write checkpoints through `checkpoints.py` and training metadata through `metadata.py`.
- Predict rawData/costs using the latest in-memory trained state.

## I/O Format
- `train(generation_index, started_at=None)` returns a `SurrogateState`.
- `predict_population(population)` returns `(costs, intervals)` for each normalized input row.
- `predict_rawdata_slot_members_at_coordinates(...)` returns physical member values
  shaped `[member, sample, *query_shape]` for one slot.

## Non-Obvious Techniques
- Prediction must not auto-train. If `_STATE` is absent, prediction raises and optimizer fallback handles it.
- Training metadata is recorded after checkpoint writing so metadata can point at completed artifacts.
- State keys include effective workspace paths, active strategy signature, and
  `conditional-inr`; direct API calls without an active strategy use one stable
  standalone namespace.
- Recovery scans only the active strategy/component namespace and accepts a
  committed unique manifest whose artifacts, signature, parameter normalization
  definition, query table, and current training configuration all agree. Compatible
  return can recover a retained publication even when the root convenience pointer
  names another strategy. Incompatible/inactive artifacts are left untouched and cause
  cold-train behavior.
- Stored-grid queries reuse the exact legacy coordinate normalization and scaler
  entries. Off-grid queries linearly interpolate target mean/scale, clamp scaler
  extrapolation to endpoint values, and leave the decoder coordinate unclipped.
- Current INR checkpoints encode three rawData coordinate columns. Dimensions
  beyond the third may retain their full stored grid but cannot yet be changed by
  this query API.

## Mutability Profile
- Data-flow details may evolve, but scheduler, checkpoint, metadata, and type responsibilities should stay in their own files.
