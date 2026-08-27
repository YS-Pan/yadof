# 2026-08-27 21:20 - Hierarchical CAE Gate 4 Development Result

## Context

- TODO 082608 requested a rawData-first hierarchical convolutional autoencoder with
  a joint parameter-latent predictor, optional groups, full-grid reconstruction,
  coordinate readout after a separate gate, and 1000/2000-design evidence.
- A subsequent user requirement added a medium-scale anti-noise MVP after a 1929-row
  Chrono audit showed parameter-dependent chatter/failure regimes rather than
  ordinary measurement noise. The change had to preserve original rawData/current
  cost, keep task diagnostics outside core, and be preregistered before any future
  offline-test access.

## Change

- Added the opt-in `hierarchical_cae()` component with fixed named-field schema,
  scalar/Conv1d/Conv2d codecs, global/optional-group/field-private latents, staged
  design-level training, shared-codec predictor members, full rawData/current-cost
  inference, atomic checkpoints, scheduler isolation, coherent finite posterior
  draws, and applicability diagnostics.
- Added a versioned JSON-safe quality/regime protocol. Explicit assessment precedes
  declarative diagnostics, morphology is an optional missing-diagnostic fallback,
  loss aggregates at design-by-field level, low-trust fields are isolated from
  shared fusion, and chatter/failure residuals use a gated private path. All policy,
  label, head, threshold, and loss semantics enter component/checkpoint identity.
- Extended read-only recorded-data/session training views with direct NPZ basenames
  and aligned copied job metadata. Existing conditional-INR training, checkpoints,
  mean/min-max behavior, GPSAF selection, and rawData evidence were not changed.
- Added Gate 0 v2--v5 preregistration, dataset/validation tools, deterministic
  assessment, threshold-scope validation, and unit/integration/package tests. The
  benchmark fingerprint now excludes transient Python bytecode/cache files.
- Updated architecture, module/file blueprints, terminology, user guidance, and the
  082608/082609/082611/082612 handoffs to reflect the implemented development
  boundary and its failed gate.

## Rationale

- A design may contain noisy curves and useful scalars, so robust aggregation must
  reduce by field rather than reject the whole row. Masking shared tokens and
  gating a field-private residual limits high-frequency leakage structurally while
  retaining physical failure evidence for `calc_cost.py`.
- Task-owned declarative rules keep Chrono-specific release/contact semantics out of
  reusable core and make every training label reproducible through semantic
  identity. Regime uncertainty remains epistemic/structural and does not invent
  independent observation noise.
- Thresholds were sealed only from the legal development-validation partition.
  Failed results are retained without relaxing the preregistered limits.

## Impact

- One authorized real campaign completed 6/6 cells and 12000 attempted evaluations;
  each case sealed 2800 designs into development/calibration/offline-test partitions.
- One validation process completed 116/116 cells in 10501.691 seconds with exit 0.
  It did not launch a simulator or access calibration/offline-test locators.
- Gate 0 v5 rejected the first production candidates on field-macro/single-field
  representation guards and rejected the gated residual on clean leakage, smooth
  roughness, and its comparison to shared isolation. Classifier AUPRC/Brier/ECE
  diagnostics alone passed their development thresholds.
- The code is an installed experimental baseline, not a production recommendation.
  TODO 082608 remains active and is not archived.

## Follow-Up

- A new preregistration version may compare a bounded regime-specialized or
  mixture-of-experts architecture because v5 provides the required leakage trigger.
- Coordinate readout/viewer work requires a later full-grid pass plus legally
  sealed stored-grid/off-grid/resource thresholds.
- 082609 must calibrate applicability only for a passing architecture on independent
  calibration designs. 082611 must consume that typed capability with a frozen
  exploitation policy and an explicit real-exploration quota. Offline/formal tests
  remain unopened until their upstream gates pass.
