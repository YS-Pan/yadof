# 2026-08-28 14:31 - Remove hash locks from benchmark/CAE simplification plan

## Context

- The benchmark/CAE simplification handoff initially treated eight historical
  experiment runners as permanently byte- and path-frozen because v4--v8
  preregistration validators compare their current repository paths with recorded
  SHA-256 values.
- The user clarified that all hash-lock requirements must be removed. Earlier
  project policy already made source fingerprints provenance rather than semantic
  compatibility or scientific rejection rules.

## Change

- Revised the active simplification toDo so source, artifact, wheel, runner, and
  manifest digests may be retained only as non-authoritative provenance and cannot
  reject edits, refactors, replay, resume, compatibility, or completion.
- Changed the eight legacy hierarchical-CAE runners from permanent historical
  exceptions into migration-and-deletion targets. Old plans, receipts, numerical
  thresholds, and results remain historical records, but their source hashes do not
  lock the current worktree.
- Replaced current-worktree fingerprint checks for benchmark resume with a planned
  run-local execution snapshot. Old runs without such a snapshot require an
  explicit restart or migration decision rather than a source-hash refusal.
- Updated the target structure, phased work, risks, and quantitative goals. The
  target now removes all 7,254 legacy-runner lines and reduces the reviewed subtotal
  by at least 41.5% even when a new experiment engine is required.

## Rationale

- Historical reproducibility belongs to Git revisions, explicit run-local
  snapshots, saved inputs, and recorded results. Requiring the latest checkout to
  retain old source bytes conflates provenance with current architecture and
  prevents ordinary cleanup.
- Scientific conclusions and thresholds can remain historically truthful without
  keeping obsolete validators as active hash gates.

## Impact

- Only the future-work handoff and this change record changed. No product code,
  benchmark runner, preregistration artifact, receipt, simulator, or runtime result
  was modified.
- The plan remains manual and still requires explicit user authorization before
  implementation.
