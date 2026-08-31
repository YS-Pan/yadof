# File blueprint: src/yadof/surrogate/posterior.py

## Intent

- Define one lightweight, backend-neutral joint rawData posterior surface suitable
  for future sample-consuming acquisition strategies.

## Functionalities

- Publish runtime-checkable posterior-surrogate, schema-bearing persistent-sampler,
  and candidate-chunk posterior protocols plus one function-draw container.
- Allow sampler creation to receive caller-owned explicit training data; concrete
  adapters may use it for schema identity but the protocol never materializes or
  scans campaign evidence itself.
- Validate JSON-safe diagnostics: kind, requested/actual draws, seed, stable
  draw/source IDs, schema/state/strategy signatures, approximation limitations,
  observation-noise status, exact selectors, candidate/failure counts, nominal
  support, per-prediction effective support, optional explicit calibration method
  and artifact hash, and honest finite versus continuous/unknown support.
- Build a semantic capability block containing the protocol version, backend
  distribution/version, posterior/support kinds, and all controlled parameters.
- Stream candidate chunks and then individual rawData draws through an injected
  `RawDataCostProjector`, retaining only joint objective samples, validity, and
  bounded diagnostics.

## Non-Obvious Techniques

- Sampler creation fixes function identities. `predict()` never reselects a member,
  weight state, mask, or latent noise per row/field/objective; candidate permutation
  and chunking only reorder/partition the same values.
- Unique finite support counts distinct source functions, not requested draws.
  Continuous or unknown support uses `None` rather than a fabricated integer.
- Final streaming diagnostics count only distinct sources whose complete draw is
  valid for every requested candidate after inference and current-cost projection;
  repeated draws cannot conceal support loss.
- Empty populations do not call the backend. A chunk-level backend/contract failure
  becomes conservative invalid samples, never favorable acquisition evidence.

## Invariants

- Import only core Python/NumPy and lightweight job-template types. Parent
  `yadof.surrogate` and `yadof.optimize` imports must not load Torch, BoTorch,
  concrete surrogate runtimes, or pymoo algorithms.
- The file never records predicted rawData and does not implement CAE, concrete
  conditional-INR inference, calibration mathematics, or acquisition. It only
  carries validated calibration diagnostics produced by the separate adjunct.
