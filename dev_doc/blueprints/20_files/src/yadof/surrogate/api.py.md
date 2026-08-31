# File blueprint: src/yadof/surrogate/api.py

## Intent
- Keep `yadof.surrogate` public calls behind one small API surface.
- Expose lazy conditional-INR, deterministic PCA/SVD, and opt-in hierarchical-CAE components plus direct
  rawData-first model operations without importing Torch at parent-package import.
- Re-export the lightweight joint rawData posterior protocol, diagnostics,
  semantic-capability helper, signature-bound calibration adjunct, and streaming
  projection helper without importing an optional backend.

## Functionalities
- Construct `conditional_inr()` with validation, semantic identity, explicit
  training-data materialization, scheduler gate/start/finish, readiness, and typed
  rawData prediction methods required by generation-local GPSAF.
  All mathematical/training/backend values are explicit keyword-only factory
  arguments stored in a private frozen settings snapshot.
- Construct `conditional_inr_posterior()` as a separate semantic wrapper that
  delegates the typed lifecycle/prediction calls and lazily creates a persistent
  finite-member rawData sampler from caller-owned training evidence.
- Construct `pca_svd()` from one authoritative keyword-only settings path. Its
  low-level codec/oracle methods are diagnostic-only. Its explicit
  `training_data()`, `fit()`/`start_fit()`, `recover()`, and typed `predict()` paths
  consume caller-owned data/state/snapshot values. `predict_for_selection()`
  satisfies the lightweight deterministic-provider protocol, recovers only the
  exact caller-supplied training state, reconstructs full named rawData, and returns
  the Stage 4 DTO for explicit pool binding. It exposes no
  posterior/readiness methods.
- Construct `hierarchical_cae()` from selector-keyed groups/layouts/axis encodings,
  one `data_filter_mode` selector that defaults to `none`, a mode-specific optional
  versioned `FrequencyFilter`, explicit device/training kwargs, and an internal
  `CAETrainConfig`. Mode `frequency` requires the filter; the default mode
  rejects one so filtering cannot be enabled through a second implicit route. The component
  owns full-grid train/recover/predict, finite joint draws, uncalibrated applicability
  prediction, and an optional architecture-v2 all-axis coordinate readout. A selected
  frequency filter enables the regime head and default robust cap; a regime head without
  that mode is rejected. `predict_field_at_coordinates()` is viewer/off-grid-only,
  returns typed member/mean values, and leaves full-grid output authoritative. Its
  deterministic selection lifecycle consumes the same caller-owned
  `SurrogateTrainingData` as PCA/SVD and conditional-INR.
- Lazily forward `train()`, `predict_population()`, `has_trained_state()`, and
  `latest_state_generation()` to `conditional_inr/runtime.py`.
- Lazily forward scheduler calls, including `deactivate_workspace()`, to
  `conditional_inr/scheduler.py`.
- Keep `RawDataPosteriorSurrogate`, persistent sampler/posterior/draw types, honest
  support diagnostics, and `project_rawdata_sampler()` on the explicit public
  surface. Sampler creation may receive explicit training data for schema identity;
  consumers validate runtime-checkable protocols rather than scattering implicit
  attribute probes.
- Re-export immutable spread/applicability calibration records, the self-verifying
  artifact, conservative fit helpers, and the coherent calibrated-sampler wrapper.
  These remain NumPy-only and do not make hierarchical CAE a production default.

## I/O Format
- PCA/SVD, conditional-INR, and hierarchical-CAE selection-provider methods return
  `SurrogatePrediction`; the optimizer binder, not the component, owns conversion to
  candidate-aligned `PredictedCostRows`. Retained `predict_population()` tuples
  remain only for closed legacy callers until cutover.
- Posterior prediction returns complete named rawData function draws; streaming
  projection returns `[draw,candidate,objective]` costs and `[draw,candidate]`
  validity without recording predicted evidence.
- Scheduler functions return status objects with action, pending generation, latest completed generation, and optional error text.
- Global deactivation also drains/releases PCA/SVD and hierarchical-CAE state while preserving
  the conditional-INR return contract used by existing callers.

## Non-Obvious Techniques
- GPSAF calls the injected component only; it does not import concrete surrogate runtime.
- Explicit deterministic selection asks each component only for its latest trained
  generation and compatible prediction. Scheduler start/wait is reached solely
  through the program-owned training helpers.
- The component semantic version changes whenever architecture/scaler semantics
  would make retained weights unsafe to reuse.
- Factory defaults are validated by the same path as explicit values. Nested task
  declarations are copied into tuples/read-only mappings before identity use.
- Hierarchical data-filter selection is dispatched only inside its private
  `data_filtering/` package. Future implementations extend that local mode boundary
  rather than adding ambient config or a package-global registry.
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
