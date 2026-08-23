# File blueprint: src/yadof/surrogate/api.py

## Intent
- Keep `yadof.surrogate` public calls behind one small API surface.
- Expose a lazy conditional-INR component plus direct rawData-first model and
  staggered-training operations without importing Torch at parent-package import.

## Functionalities
- Construct `conditional_inr()` with validation, semantic identity, scheduler gate,
  train-after-submit, readiness, and rawData prediction methods required by GPSAF.
- Lazily forward `train()`, `predict_population()`, `has_trained_state()`, and
  `latest_state_generation()` to `conditional_inr/runtime.py`.
- Lazily forward scheduler calls, including `deactivate_workspace()`, to
  `conditional_inr/scheduler.py`.

## I/O Format
- Prediction returns optimizer-facing `(costs, intervals)` rows.
- Scheduler functions return status objects with action, pending generation, latest completed generation, and optional error text.

## Non-Obvious Techniques
- GPSAF calls the injected component only; it does not import concrete surrogate runtime.
- Parent import preloads only the empty private-package marker before rebinding the
  same-named public factory, preserving both lazy Torch loading and callable API
  stability.

## Mutability Profile
- Add public surrogate functions here only when another core module needs them.
