# File blueprint: src/yadof/surrogate/api.py

## Intent
- Keep `yadof.surrogate` public calls behind one small API surface.
- Expose a lazy conditional-INR component plus direct rawData-first model and
  staggered-training operations without importing Torch at parent-package import.
- Re-export the lightweight joint rawData posterior protocol, diagnostics,
  semantic-capability helper, and streaming projection helper without importing an
  optional backend.

## Functionalities
- Construct `conditional_inr()` with validation, semantic identity, scheduler gate,
  train-after-submit, readiness, and rawData prediction methods required by GPSAF.
- Construct `conditional_inr_posterior()` as a separate semantic wrapper that
  delegates legacy lifecycle/prediction calls and lazily creates a persistent
  finite-member rawData sampler.
- Lazily forward `train()`, `predict_population()`, `has_trained_state()`, and
  `latest_state_generation()` to `conditional_inr/runtime.py`.
- Lazily forward scheduler calls, including `deactivate_workspace()`, to
  `conditional_inr/scheduler.py`.
- Keep `RawDataPosteriorSurrogate`, persistent sampler/posterior/draw types, honest
  support diagnostics, and `project_rawdata_sampler()` on the explicit public
  surface. A future consumer validates the runtime-checkable protocol rather than
  scattering implicit attribute probes.

## I/O Format
- Prediction returns optimizer-facing `(costs, intervals)` rows.
- Posterior prediction returns complete named rawData function draws; streaming
  projection returns `[draw,candidate,objective]` costs and `[draw,candidate]`
  validity without recording predicted evidence.
- Scheduler functions return status objects with action, pending generation, latest completed generation, and optional error text.

## Non-Obvious Techniques
- GPSAF calls the injected component only; it does not import concrete surrogate runtime.
- The component semantic version changes whenever architecture/scaler semantics
  would make retained weights unsafe to reuse.
- Posterior capability identity is separate and must be nested only in a strategy
  that explicitly selects it; the implemented adapter must not cold-invalidate the
  current conditional-INR GPSAF checkpoint identity.
- Parent import preloads only the empty private-package marker before rebinding the
  same-named public factory, preserving both lazy Torch loading and callable API
  stability.

## Mutability Profile
- Add public surrogate functions here only when another core module needs them.
