# 2026-07-27 17:17 - Add Timeout Condor Machine Fallback

## Context

- Worker support records authoritative `execute_machine` metadata at workflow
  startup, but a held or removed timeout commonly cannot transfer
  `individual_metadata.json` back to the submit host.
- Per-job Condor user logs already retain event-001 execution segments and normally
  include both `SlotName` and the execute-address alias.
- In the inspected workspace, 172 of 208 timeout records had such an execution
  site; the other 36 never executed and correctly had no machine.

## Change

- Extended Condor execution-log parsing to retain the active segment's machine and
  slot and to retrieve the most recent segment for an allowed-duration hold.
- Recorded `condor_execute_machine`, optional `condor_slot_name`, and
  `condor_execute_machine_source = "condor_user_log"` for timeout fallbacks.
- Captured the active site before bounded removal for yadof watchdog and
  whole-generation timeouts; queued jobs without an active segment remain
  unassigned.
- Changed viewTime machine lookup to prefer worker `execute_machine`, then the
  Condor fallback, then legacy compatibility fields.
- Added read-only historical fallback from each recorded timeout's durable
  `condor_log_tail`; it recognizes active removal, `condor_rm` eviction, and a
  terminal execution that was not collected before the generation deadline, while
  distinguishing ordinary eviction back to the queue. It never rewrites recorded
  data.
- Added focused active/removed/terminated/evicted/held/queued/precedence tests and
  updated current architecture, terminology, blueprints, and agent guidance.

## Rationale

- The job-local event log is already durable, workspace-scoped evidence and avoids
  adding another scheduler query during timeout cleanup.
- Keeping separate fields and an explicit source preserves the distinction between
  worker-observed identity and scheduler-observed fallback provenance.
- Selecting only the active segment for a generation deadline prevents a previously
  evicted machine from being assigned to a job that was queued when it timed out.
- Historical central-timeout rows may contain the removal/termination event written
  immediately after their last active segment; retaining that terminal site's
  provenance recovers the machine without treating an ordinary eviction as a
  timeout site.

## Impact

- Timed-out jobs that actually ran can now appear under their Condor-observed
  machine in viewTime even when worker metadata did not transfer.
- Existing compatible timeout history benefits immediately when its stored log tail
  still contains the relevant execution and terminal events. In the inspected
  workspace this resolves 172 of 208 timeout rows; the remaining 36 never executed.
- Worker metadata remains authoritative, normal completed/error transport is
  unchanged, and never-executed jobs still display as `unknown`.

## Follow-Up

- None.
