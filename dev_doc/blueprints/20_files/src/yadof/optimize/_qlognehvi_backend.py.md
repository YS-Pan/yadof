# File blueprint: src/yadof/optimize/_qlognehvi_backend.py

## Intent

- Adapt fixed baseline truth and aligned empirical candidate objective draws to
  BoTorch's mature qLogNEHVI numerical implementation.

## Functionalities

- Validate multi-objective `[0,1]` minimization semantics, normalized unique
  baseline/candidate rows, explicit non-repeating q batches, and a finite reference
  point.
- Reject every incomplete or out-of-contract MC draw as a whole; preserve finite
  `1.0` as a valid worst task cost.
- Repeat fixed observed baseline costs across retained draws, negate minimization
  costs/reference once, and serve the aligned values from a lookup
  `EnsembleModel`/`EnsemblePosterior`.
- Enumerate supplied draws exactly once, delegate qLogNEHVI hypervolume,
  partitioning, smoothing, and log-improvement to BoTorch, and group only equal-q
  discrete evaluation calls.
- Apply optional finite effective-support warning/rejection and emit compact
  backend, shape, mask, support, device, timing, and tensor-memory diagnostics.

## Invariants

- No custom hypervolume estimator, gradient `optimize_acqf`, pending points,
  outcome constraints, candidate-pool implementation, orchestration, evaluator, or
  recorder integration.
- Seed is recorded and the sampler does not break upstream joint draw pairing by
  independently resampling candidates or objectives.
- Optional Torch/BoTorch imports occur only after the explicit lightweight wrapper
  is called.
