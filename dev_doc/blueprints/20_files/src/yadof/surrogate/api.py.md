# File blueprint: src/yadof/surrogate/api.py

## Intent
- Keep `yadof.surrogate` public calls behind one small API surface.
- Expose lazy conditional-INR and opt-in hierarchical-CAE components plus direct
  rawData-first model operations without importing Torch at parent-package import.
- Re-export the lightweight joint rawData posterior protocol, diagnostics,
  semantic-capability helper, signature-bound calibration adjunct, and streaming
  projection helper without importing an optional backend.

## Functionalities
- Construct `conditional_inr()` with validation, semantic identity, scheduler gate,
  train-after-submit, readiness, and rawData prediction methods required by GPSAF.
- Construct `conditional_inr_posterior()` as a separate semantic wrapper that
  delegates legacy lifecycle/prediction calls and lazily creates a persistent
  finite-member rawData sampler.
- Construct `hierarchical_cae()` from selector-keyed groups/layouts/axis encodings,
  an optional versioned `RawDataQualityPolicy`, and `CAETrainConfig`. The component
  owns full-grid train/recover/predict, finite joint draws, uncalibrated applicability
  prediction, and an optional architecture-v2 all-axis coordinate readout. A selected
  quality policy enables the regime head and default robust cap; a regime head without
  a policy is rejected. `predict_field_at_coordinates()` is viewer/off-grid-only,
  returns typed member/mean values, and leaves full-grid output authoritative.
- Lazily forward `train()`, `predict_population()`, `has_trained_state()`, and
  `latest_state_generation()` to `conditional_inr/runtime.py`.
- Lazily forward scheduler calls, including `deactivate_workspace()`, to
  `conditional_inr/scheduler.py`.
- Keep `RawDataPosteriorSurrogate`, persistent sampler/posterior/draw types, honest
  support diagnostics, and `project_rawdata_sampler()` on the explicit public
  surface. A future consumer validates the runtime-checkable protocol rather than
  scattering implicit attribute probes.
- Re-export immutable spread/applicability calibration records, the self-verifying
  artifact, conservative fit helpers, and the coherent calibrated-sampler wrapper.
  These remain NumPy-only and do not make hierarchical CAE a production default.

## I/O Format
- Prediction returns optimizer-facing `(costs, intervals)` rows.
- Posterior prediction returns complete named rawData function draws; streaming
  projection returns `[draw,candidate,objective]` costs and `[draw,candidate]`
  validity without recording predicted evidence.
- Scheduler functions return status objects with action, pending generation, latest completed generation, and optional error text.
- Global deactivation also drains/releases hierarchical-CAE state while preserving
  the conditional-INR return contract used by existing callers.

## Non-Obvious Techniques
- GPSAF calls the injected component only; it does not import concrete surrogate runtime.
- The component semantic version changes whenever architecture/scaler semantics
  would make retained weights unsafe to reuse.
- Posterior capability identity is separate and must be nested only in a strategy
  that explicitly selects it; the implemented adapter must not cold-invalidate the
  current conditional-INR GPSAF checkpoint identity.
- Posterior exploitation identity/readiness is a second, separate typed contract.
  Both current posterior components return performance-not-accepted,
  uncalibrated, non-transferable blockers and never forward experimental
  probabilities into acquisition.
- Parent import preloads only the empty private-package marker before rebinding the
  same-named public factory, preserving both lazy Torch loading and callable API
  stability.
- The hierarchical component remains a development surface after Gate 0 v5 failure.
  Gate 0 v6/v7 proves only coordinate/viewer mechanism execution; the API carries
  `experimental / performance-not-accepted` semantics and does not imply production
  qNEHVI readiness. Gate 0 v8's six fail-closed calibration artifacts likewise
  create no current exploitation capability.

## Mutability Profile
- Add public surrogate functions here only when another core module needs them.
