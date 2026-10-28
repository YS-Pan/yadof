# 2026-09-30 12:28 - Use Condor Pending Progress and Expand Drain Controls

## Context

- The Windows Condor GUI parsed yadof's population outcome lines but did not use
  HTCondor's `pending=N/T` progress emitted by the distributed runner.
- The GUI always issued a graceful drain and had no control to cancel an active
  drain request.

## Change

- Drive the GUI progress bar from Condor pending counts when available, deriving
  completed work as `total - pending`; retain generation outcome progress for
  fast/local runs.
- Display the selected slot's `Machine` ClassAd attribute alongside `Name`.
- Add a graceful/quick/fast selection dialog and a cancel-drain action, both
  targeting the selected slot's `Machine` value. If HTCondor cannot locate the
  StartD by that name, retry with the same ClassAd's full `MyAddress`.

## Impact

- Updated `yadof.tools.condor_gui`, its tools blueprint, and the Windows GUI user
  guide. Drain cancellation uses `condor_drain -cancel <Machine>` with the same
  lookup fallback.

## Follow-Up

- Wheel build, installed import-origin checks, read-only Condor status query, and
  source syntax checks passed. Automated tests were not run in this change.
