# File blueprint: src/yadof/surrogate/runtime.py

## Intent
- Own surrogate training and prediction data flow while preserving `normalized variables -> rawData -> cost`.

## Functionalities
- Load training bundles from `recorded_data.api`.
- Flatten numeric rawData slots into conditional-INR query tables and reconstruct predicted rawData.
- Apply task-owned rawData importance weights.
- Train the INR ensemble through `modeling.py`.
- Write checkpoints through `checkpoints.py` and training metadata through `metadata.py`.
- Predict rawData/costs using the latest in-memory trained state.

## I/O Format
- `train(generation_index, started_at=None)` returns a `SurrogateState`.
- `predict_population(population)` returns `(costs, intervals)` for each normalized input row.
- `evaluate_historical_errors()` returns relative historical error rows from the latest trained state.

## Non-Obvious Techniques
- Prediction must not auto-train. If `_STATE` is absent, prediction raises and optimizer fallback handles it.
- Training metadata is recorded after checkpoint writing so metadata can point at completed artifacts.

## Mutability Profile
- Data-flow details may evolve, but scheduler, checkpoint, metadata, and type responsibilities should stay in their own files.
