# File blueprint: src/yadof/surrogate/hierarchical_cae/posterior_adapter.py

## Intent

- Expose a persistent finite-member joint rawData posterior over the recovered
  hierarchical CAE predictor ensemble.

## Functionalities

- Fix seeded permutation-cycle member/source IDs through the shared finite-member
  primitive when the sampler is created.
- Accept the common explicit training-data argument for protocol parity. The
  recovered CAE state's frozen schema is already authoritative, so this adapter
  does not reinterpret or reopen that evidence.
- Evaluate each selected member across complete candidate batches and reconstruct
  every frozen named field before returning protocol draw objects.
- Report nominal/effective finite support, component/state/schema identities,
  zero-observation-noise status, and bounded inference failures.

## Invariants

- One draw retains the same member across candidates and fields.
- Shared codecs do not inflate support beyond distinct predictor members.
- Applicability/regime uncertainty is structural and never sampled as independent
  candidate/field Gaussian noise.
