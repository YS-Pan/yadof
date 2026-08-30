# File blueprint: src/yadof/recorded_data/dataset.py

## Intent

- Expose immutable evidence metadata/provenance and current-task cost
  interpretations without creating another persistence layer.
- Preserve candidate, row, design, lineage, and interpretation identities through
  filtering, transformation, reordering, and consumer joins.

## Functionalities

- Build durable datasets from one tolerant finalized-segment catalog and live
  datasets from one campaign-state snapshot.
- Represent original, pending, failed, committed, and explicitly derived rows with
  immutable JSON-safe metadata and bounded diagnostics.
- Keep committed rawData behind lazy `SegmentReference` loaders; selection, copy,
  filtering, and joins perform no decode.
- Derive transient owned rawData rows with deterministic
  parent/operation/parameter/ordinal/content lineage.
- Calculate one objective-schema/fingerprint-bound `CostTable` through one frozen
  interpreter, decoding and releasing at most one row at a time.
- Retain succeeded, failed, not-applicable, and missing statuses; provide the sole
  table adapter that maps non-successful rows to correct-width optimizer `inf`.

## Invariants

- Original `row_id`, `evidence_id`, and durable `candidate_id` are identical.
  `design_key` expresses physical-design equality only and never sample identity.
- Derived rows retain root evidence identity and explicit lineage but never publish
  themselves or enter committed optimizer history.
- Cost joins validate row and root evidence identity rather than position or job
  name; interpretation identity also binds task fingerprint and objective schema.
- Successful costs and normalized variables are finite and have the declared
  objective width; every other status keeps `costs=None` and bounded diagnostics.
- Reinterpretation changes only the cost view. Evidence records, rawData bytes, and
  segment identity remain unchanged.
