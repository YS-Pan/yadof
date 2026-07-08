# File blueprint: project/recorded_data/records.py

## Intent
- Persist real individual records and compact optimization-level metadata.

## Functionalities
- Record individual raw variables/rawData/job metadata.
- Record generation-level metadata.
- Record surrogate-training metadata through `record_surrogate_metadata()`.

## I/O Format
- Individual rows go to `indMeta.jsonl`.
- Optimization and surrogate-training rows go to `optMeta/optMeta.jsonl`.
- Surrogate rows use `record_type = "surrogate_training"`.

## Non-Obvious Techniques
- Surrogate-training metadata is diagnostic optimization metadata. It must not be mixed with real individual rawData evidence, and it must not persist derived objective costs as source data.

## Mutability Profile
- Metadata schemas should change cautiously because tools inspect these rows.
