# 2026-09-30 10:55 - Sortable viewerror with worker and job folder navigation

## Context

The HTCondor GUI's `viewerror` button displayed failure rows as plain text. Users
could not sort them, see the execute worker alongside each row, or navigate from a
failure to its prepared job files.

## Change

- Display typed `view_time.build_rows()` failure data in a sortable Tk table with
  time, worker, job, error type, and message columns.
- Resolve each job name under the configured workspace jobs directory and open its
  folder on a row double-click. Missing or escaping paths produce a diagnostic.
- Keep history interpretation in `view_time`; update the GUI documentation and
  focused installed-package tests for sorting and navigation.

## Rationale

The time tool already owns failure classification and execute-machine attribution.
Keeping a typed row in the GUI preserves the exact job identity when rows are
reordered and avoids reading mutable job-local files to classify errors.

## Impact

The change affects the Windows Condor GUI and its user-facing documentation. It
does not alter recorded evidence, job execution, or the time-view PNG and summary.

## Follow-Up

Focused GUI tests pass. The complete local suite has six unrelated failures: five
posterior-assisted tests require the absent optional `botorch` dependency, and one
recording backpressure counter assertion reports zero. These require separate
environment or recording investigation.
