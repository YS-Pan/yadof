# 2026-07-30 11:36 - Stream Local Workflow Progress

## Context

- Local workflow subprocesses wrote stdout and stderr only into captured metadata
  tails after completion, so long simulator stages appeared silent in PowerShell.
- Concurrent simulator jobs need an unambiguous prefix so their output can be
  distinguished without giving up the existing diagnostic capture.

## Change

- Added progress-mode pipe-draining threads to the local runner.
- Complete stdout and stderr lines are forwarded immediately with job and stream
  prefixes when `YADOF_PROGRESS` is enabled.
- Preserved the same captured output used by metadata tails and retained existing
  timeout process-tree cleanup.
- Added focused local evaluation coverage and updated user, architecture, and
  module/test blueprint documentation.

## Rationale

- Draining both pipes continuously avoids subprocess pipe deadlocks and provides
  useful live feedback without changing normal non-progress execution.
- Prefixing under one output lock keeps concurrent job lines identifiable and
  prevents partial cross-thread writes.

## Impact

- `yadof run --progress` and other local calls using `YADOF_PROGRESS` now show
  task workflow output while it is produced.
- Jobs continue to persist stdout/stderr tails for later failure diagnosis.

## Follow-Up

- Real external simulators may write detailed solver output to their own logs;
  task workflows should emit concise stage lines when those milestones matter.
