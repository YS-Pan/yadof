# File blueprint: src/yadof/recorded_data/records.py

## Intent
- Persist real individual records and compact optimization-level metadata.

## Functionalities
- Record individual raw variables/rawData/job metadata.
- Record a population batch with one archive/manifest publication.
- Record generation-level metadata.
- Record surrogate-training metadata through `record_surrogate_metadata()`.
- Require an immutable `RecordedDataPaths` value derived from the caller's workspace;
  never read module-global source/package paths.

## I/O Format
- Individual rows go to `indMeta.jsonl`.
- Optimization and surrogate-training rows go to `optMeta/optMeta.jsonl`.
- Surrogate rows use `record_type = "surrogate_training"`.

## Non-Obvious Techniques
- Surrogate-training metadata is diagnostic optimization metadata. It must not be mixed with real individual rawData evidence, and it must not persist derived objective costs as source data.
- Individual writes validate names/status/source files before taking the workspace
  lock, replace that job's archive members, scrub/promote metadata, then atomically
  update JSONL. Duplicate jobs require explicit overwrite.
- Batch writes reject duplicate job names, preserve request order, copy existing
  archive state at most once, and publish all new evidence atomically. Evaluation
  orchestration may fall back to single writes when batch preparation fails so
  individual failure isolation remains intact.

## Mutability Profile
- Metadata schemas should change cautiously because tools inspect these rows.
