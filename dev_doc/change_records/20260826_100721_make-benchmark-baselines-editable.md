# 2026-08-26 10:07 - Make Benchmark Baselines Editable

## Context

- Exact baseline creation-version and task-fingerprint checks prevented the 0.4.1
  environment from running templates originally created by 0.4.0.
- The user removed the frozen-baseline policy, required baselines to remain editable
  at any time, and requested removal of fingerprint suffixes from directory names.
- Existing runs still need one coherent task definition across all cells even when
  the source template changes later.

## Change

- Replaced fingerprint-derived baseline identities with semantic
  `baselines/<provider>/<baseline-id>` names. The selected directories are now
  `ngspice/saw-ladder`, `chrono/trebuchet`, and
  `test-com/synthetic-antenna`; the retained Chrono regression template is
  `chrono/trebuchet-path-regression`.
- Made manifest yadof versions and task fingerprints creation provenance rather
  than current-content locks. Preflight validates runtime cleanliness, the current
  installed `yadof check`, resources, strategies, disk, and package installation.
- Added run creation snapshots under
  `<run-root>/inputs/baselines/<case>/workspace`. Snapshot creation refuses a task
  change between preflight and copying; cell materialization, verification,
  collection, reporting, and resume use the run-local snapshot rather than the
  editable source template.
- Updated benchmark, user, architecture, blueprint, terminology, and agent guidance
  to distinguish mutable baseline templates from immutable run-local evidence.

## Rationale

- Semantic names remain readable as task content evolves and avoid directory churn
  caused only by fingerprints.
- Snapshot-on-run permits unrestricted source-template editing without allowing one
  benchmark run to mix task definitions across cells or replacements.
- Keeping actual task/package fingerprints in the immutable run spec preserves
  auditability without treating the source template as permanent evidence.

## Impact

- Benchmark automation tests passed 50 checks with fresh external pytest state,
  including prior-patch provenance, mutable-source snapshot isolation, materialized
  cell inputs, visualization grouping, and semantic baseline identity.
- The complete `performance` plan still contains 18 measured cells and 36,000
  attempted real evaluations. Its live preflight passed all 13 checks under yadof
  0.4.1 after the rename and policy change.
- Baseline scientific task files were renamed with their directories but not
  otherwise changed. Existing generated run evidence was not rewritten or deleted.

## Follow-Up

- Runs created before this snapshot contract retain their historical evidence but
  do not retroactively acquire `inputs/baselines/`; the changed runner fingerprint
  already prevents treating them as resumable by the new implementation.
