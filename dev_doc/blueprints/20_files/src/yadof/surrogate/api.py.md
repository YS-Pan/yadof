# File blueprint: src/yadof/surrogate/api.py

## Intent
- Keep `yadof.surrogate` public calls behind one small API surface.
- Expose both rawData-first model operations and staggered-training scheduler operations without requiring callers to import internal files.

## Functionalities
- Re-export `train()`, `predict_population()`, `evaluate_historical_errors()`, `has_trained_state()`, and `latest_state_generation()` from `runtime.py`.
- Re-export `start_training()`, `wait_for_pending_training()`, and `ensure_fresh_enough()` from `scheduler.py`.

## I/O Format
- Prediction returns optimizer-facing `(costs, intervals)` rows.
- Scheduler functions return status objects with action, pending generation, latest completed generation, and optional error text.

## Non-Obvious Techniques
- Optimizer code should call this file only; it should not import `scheduler.py` or `runtime.py` directly.

## Mutability Profile
- Add public surrogate functions here only when another core module needs them.
