# 2026-10-21 00:25 - Condor GUI Queue Removal and Slot Job IDs

## Context

The user requested an independent queue-clear button and a task-number column for
each slot. Previously, the GUI only removed the queue as part of stopping the
optimization process, and the slot table did not request job identifiers.

## Change

- Add **清空队列** to execute `condor_rm -all` on a worker without requiring a
  workspace, stopping the optimizer process, or resetting workspace data/progress.
- Share the command implementation with the existing stop operation. Prevent
  duplicate queue-clear requests, keep workspace startup/cleanup and window close
  blocked while the command is pending, restore controls after errors or success,
  and refresh slot status after success.
- Query `JobId` in the same `condor_status` response as each slot. Display its
  `ClusterId.ProcId` string in **任务编号**, using `—` for unavailable IDs. Refresh
  replaces IDs and the slot table supports horizontal scrolling.
- Document queue-wide removal subject to HTCondor ownership/super-user permission,
  and cover command isolation, button completion/failure, duplicate requests, and
  per-slot IDs across refreshes with mocked command boundaries.

## Impact

The change stays in `yadof.tools.condor_gui` and its GUI tests, user guide, and
tools/tests blueprints. It does not alter evaluation, optimization, history, or pool
configuration contracts. No live queue-removal command is part of acceptance.
