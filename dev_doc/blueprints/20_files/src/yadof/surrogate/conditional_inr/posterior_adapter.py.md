# File blueprint: src/yadof/surrogate/conditional_inr/posterior_adapter.py

## Intent

- Adapt the existing conditional-INR ensemble to the backend-neutral persistent
  joint rawData posterior protocol without changing deterministic prediction or training.

## Functionalities

- Resolve the active trained state and require its strategy namespace to match the
  generation context.
- Recover exact direct `.npz` basenames from caller-owned
  `SurrogateTrainingData` and freeze them with the state's full-grid rawData
  templates. No session-evidence fallback exists.
- Select one ensemble member per draw through a deterministic seeded permutation-
  cycle policy and report repeated source identities honestly.
- Predict one complete member/candidate at a time through runtime's controlled
  selected-member helper, reconstruct every main field together, and retain only
  bounded failure diagnostics.

## I/O and failure contract

- `make_rawdata_sampler(context, draw_count, seed, training_data=...)` returns a
  persistent sampler. Explicit selectors require the owned training value.
- `predict(population)` returns ordered `RawDataFunctionDraw` objects aligned with
  the fixed draw IDs. Repeated candidates reuse the same result inside a call;
  permutation or external candidate chunking changes only ordering.
- A failed member/candidate produces one invalid empty structured sample for every
  draw using that member. It never borrows another member's fields. Prediction
  diagnostics distinguish nominal loaded-member support from effective distinct
  complete sources.
- A modeled non-main array is rejected because posterior axes, units, metadata,
  shape, and dtype template values must remain frozen.

## Invariants

- Full stored-grid reconstruction only; never use viewer off-grid interpolation.
- No cost callback, qNEHVI logic, recorder call, checkpoint write, calibration, or
  observation-noise invention.
- Importing the public parent remains Torch-lazy; this private module loads only
  when the explicit posterior factory creates a sampler.
- Sampler construction never scans `context.session`.
