# File blueprint: src/yadof/surrogate/calibration.py

## Intent

- Define a backend-neutral, checkpoint-bound calibration adjunct for coherent
  finite rawData posterior draws and member-level applicability probabilities.
- Keep an experimental calibration result incapable of promoting or silently
  transferring the performance-rejected hierarchical CAE architecture.

## Functionalities

- Serialize a self-verifying `PosteriorCalibrationArtifact` that binds exact
  state, strategy, schema, checkpoint-file, training-provenance, dataset,
  calibration-locator, design-ID, policy, and label/head/loss identities.
- Select conservative per-field spread multipliers from a preregistered grid using
  design-macro central-interval coverage plus a bounded multivariate energy term.
- Fit one strictly monotone logit-affine applicability mapping to every predictor
  member with independent design-level calibration evidence.
- Wrap one persistent finite sampler, scaling complete member draws around the
  empirical mean while preserving draw IDs, source IDs, candidate coherence,
  field pairing, chunking, permutations, repeated candidates, and zero noise.
- Reject stale, incomplete, failed-gate, repeated-support, or tampered artifacts
  instead of falling back to coefficients from another state.

## Non-Obvious Techniques

- A usable calibrated finite sampler must enumerate each unique source exactly
  once. Repeated sampling cannot create calibration support or preserve the exact
  empirical mean required by field-wise spread scaling.
- All fields retain one shared member axis. Field scales never resample or reorder
  that axis, and every adjusted field receives a numerical mean correction so the
  original ensemble mean remains unchanged to floating-point precision.
- Applicability calibration transforms each member before averaging and uses the
  same positive-slope mapping for all members. It does not collapse epistemic
  member spread into observation noise.
- The adjunct is immutable and non-transferable. Failed rawData gates expose only
  explicit identity-scale `uncalibrated` artifacts; failed applicability gates
  expose no slope or intercept.

## Invariants

- Import only core Python, NumPy, lightweight job-template types, posterior types,
  and the quality prediction container; never import Torch, BoTorch, a concrete
  surrogate runtime, a simulator, or task cost code.
- Calibration never changes the posterior mean, fits cost directly, reorders
  fields/objectives independently, records predicted rawData, or introduces
  per-candidate pseudo-noise.
- Artifact application requires exact runtime state/strategy/schema/support
  equality and a successful frozen calibration status.
- `experimental-performance-not-accepted` and `transferable=False` are fixed
  artifact semantics, not caller-selectable labels.
