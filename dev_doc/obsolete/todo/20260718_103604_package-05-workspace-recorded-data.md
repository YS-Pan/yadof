# Package Step 5: Workspace Recorded Data

## Context

- This is step 5 of 10 and depends on step 4 being completed and archived.
- Local evaluation can now produce workspace jobs; durable history must move out of
  the source/package tree without changing its meaning.

## Goal

- Migrate `recorded_data` to explicit workspace storage and packaged APIs.
- Preserve raw evidence, dynamic costs/normalization, locks, atomicity, diagnostics,
  and history recovery contracts.

## Guidance

- Store jobs, `indMeta.jsonl`, the zip-based `rawData.npz`, `optMeta/`, and related
  locks only below the active workspace paths. Same-named jobs in separate
  workspaces must never share records.
- Keep raw variables/rawData/metadata as durable truth and calculate cost plus
  normalized historical variables from current workspace task definitions on
  demand. Preserve workflow timing promotion, rawData metadata scrubbing, status
  normalization, invalid-data diagnostics, and failed-record visibility.
- Pass workspace/task context through public APIs rather than module globals or
  installed-source paths. Ensure query and record operations cannot reuse cached
  task/config state from another workspace.
- Retain process/file locking, atomic JSONL/archive updates, and per-individual
  record failure isolation for future local/distributed concurrency.
- Do not implement old repository-history migration or a dual reader/writer unless
  the user later requests a specific migration path.

## Verification

- Run record/query/history recovery tests in two workspaces, including identical job
  names, changed parameter ranges, changed `calc_cost.py`, invalid rawData, failed
  records, and concurrent writes.
- Verify no records, locks, archives, or temporary writes appear in site-packages or
  the source repository during installed-wheel tests.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- Workspace-local history has the current semantic and concurrency guarantees.
  Archive this file, then execute step 6.
