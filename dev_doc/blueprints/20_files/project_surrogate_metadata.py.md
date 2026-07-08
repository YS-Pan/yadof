# File blueprint: project/surrogate/metadata.py

## Intent
- Convert surrogate training outcomes into compact recorded-data metadata rows.

## Functionalities
- Build success metadata from `SurrogateState` and training timing.
- Build failure metadata from exceptions.
- Write rows through `recorded_data.api.record_surrogate_metadata()` when available, with a safe fallback to optimization metadata.

## I/O Format
- Metadata rows use `record_type = "surrogate_training"`.
- Rows include generation index, status, timing, sample/query/member counts, error summaries, checkpoint file, and artifact directory.

## Non-Obvious Techniques
- Surrogate metadata is not individual evidence and must not enter `indMeta.jsonl`.
- Metadata should stay JSON-safe and avoid storing full arrays, populations, or costs.

## Mutability Profile
- Add fields when they help diagnose training/runtime behavior, but keep rows compact.
