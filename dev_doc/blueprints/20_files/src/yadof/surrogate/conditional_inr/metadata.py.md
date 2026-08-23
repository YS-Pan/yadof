# File blueprint: src/yadof/surrogate/conditional_inr/metadata.py

## Intent
- Convert surrogate training outcomes into compact recorded-data metadata rows.

## Functionalities
- Build success metadata from `SurrogateState` and training timing.
- Build failure metadata from exceptions.
- Write rows through `recorded_data.api.record_surrogate_metadata()` when available, with a safe fallback to optimization metadata.

## I/O Format
- Metadata rows use `record_type = "surrogate_training"`.
- Rows include generation index, status, timing, sample/query/member counts, training
  policy, strategy/state/run/component identity, checkpoint manifests, and artifact
  directory. Training-fit error is not a trust metric and is not recorded.

## Non-Obvious Techniques
- Surrogate metadata is not individual evidence and must not enter evidence
  segments.
- Metadata should stay JSON-safe and avoid storing full arrays, populations, or costs.

## Mutability Profile
- Add fields when they help diagnose training/runtime behavior, but keep rows compact.
