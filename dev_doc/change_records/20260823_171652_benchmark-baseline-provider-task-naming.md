# 2026-08-23 17:16 - Name benchmark baselines by provider and task

## Context

- Benchmark baseline directories mixed case names with date-based identities, so
  their two levels did not consistently communicate the simulator/adapter and the
  optimization task.
- The requested structure makes those two meanings visible in the path while
  retaining the already validated task fingerprints and scientific workspace
  content.

## Change

- Standardized baseline paths as
  `baselines/<provider>/<task>-<12-hex-task-fingerprint-prefix>`.
- Migrated the existing inputs to `ngspice/saw-ladder-*`,
  `chrono/trebuchet-*`, and `test-com/synthetic-antenna-*`, and aligned their
  manifests and explicit TOML selections.
- Added runner validation for the path and manifest identity contract plus focused
  regression tests and current-view documentation.

## Rationale

- Provider and task are stable scientific identities, while a creation date and a
  benchmark case label do not state what executes the task or what is optimized.
- Checking the full manifest fingerprint against the directory prefix prevents a
  descriptive rename from silently selecting different task content.

## Impact

- Existing generated runs retain their immutable recorded paths and fingerprints.
- New configuration must select a baseline using the provider/task layout and a
  matching `baseline.json` identity.

## Follow-Up

- None.
