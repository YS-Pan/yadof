# 2026-07-18 19:01 - Workspace Recorded Data

## Context

- Packaged local evaluation already created jobs below an explicit workspace but
  still calculated costs directly from job-local rawData without durable package-era
  history.
- The old `project.recorded_data` implementation preserved the required evidence,
  dynamic-history, diagnostics, and concurrency ideas, but selected writable paths
  through module globals rooted beside source code.

## Change

- Copied the existing recorded-data module into `src/yadof/recorded_data` and
  replaced source-relative globals with immutable paths derived from the explicit
  `WorkspaceContext` supplied to every public operation.
- Kept raw variables/rawData/metadata as durable truth; current parameter ranges and
  `calc_cost.py` are freshly loaded for normalized-variable, cost, history, and
  surrogate-training views.
- Added workspace-keyed process locks, OS file locks, atomic same-directory JSONL/
  zip replacement, orphan archive-member recovery, status normalization, metadata
  scrubbing/timing promotion, invalid-rawData diagnostics, and failed-record
  visibility.
- Copied and simplified the evaluator recorded-data client so packaged local success,
  error, timeout, and preparation failures record best effort before returning costs
  or per-individual `inf`.
- Added two-workspace, task-edit, recovery, invalid-data, failed-record, multi-process
  archive/manifest, path-override, record-failure-isolation, and read-only installed-
  wheel coverage.
- Added current architecture, blueprint, terminology, root/user documentation, and a
  new file blueprint for `src/yadof/recorded_data/records.py`.

## Rationale

- Explicit workspace context prevents same-named jobs or freshly loaded task modules
  from contaminating another workspace and makes installed package files immutable
  code rather than accidental data directories.
- Copying the mature module before adaptation preserved the established raw-evidence
  and diagnostic semantics while allowing the package API to reject implicit legacy
  storage.
- Atomic replacement and per-path locking give local concurrency a durable contract
  that can later be reused by distributed finalization.

## Impact

- Installed `yadof` now exposes `yadof.recorded_data` Python APIs. There is still no
  installed history/view command and the source optimizer/surrogate/tools continue
  using transitional `project.recorded_data` until their ordered migrations.
- `yadof smoke-test` and packaged local population evaluation now create
  `indMeta.jsonl`, its lock, `rawData.npz` when rawData exists, and optional
  `optMeta/` only below the effective workspace record path.
- Existing repository history is not migrated or dual-read. A caller using a custom
  `RECORDED_DATA_DIR` passes the effective `load_config(...).workspace` context.

## Follow-Up

- Package step 6 can move optimizer/problem/runtime state onto these workspace-
  explicit evaluation and history APIs. It is not executed by this manual task.
