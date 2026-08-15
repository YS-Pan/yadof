# File blueprint: src/yadof/recorded_data/query_v2.py

## Intent

- Expose tolerant workspace-explicit reads over finalized v2 evidence without
  relying on mutable aggregate files.

## Functionalities

- List/filter catalog records and derive normalized variables/current costs using
  current task code.
- Load rawData samples, assemble surrogate training bundles, and report bounded
  segment/candidate diagnostics.
- Skip malformed, missing, incompatible, or non-finite candidates while preserving
  readable siblings and stable record order.

## Invariants

- Legacy JSONL/global-ZIP files and temporary segments are ignored.
- Public reads perform no repair, overwrite, or publication.
- Derived values are recalculated under the caller's current task interpretation;
  durable evidence remains unchanged.
