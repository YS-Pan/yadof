# 2026-07-26 10:17 - Integrate Errors Into Time View

## Context

- A separate error plot split closely related timing and failure information across
  two images and did not make efficient use of the time chart.
- Machine identity must describe the computer observed by the running workflow on
  the execute node, not a value inferred later on the submit host.

## Change

- Removed the standalone `view_error.py`, its `yadof view error` command, focused
  test module, and file blueprint.
- Restored failure-rate summary and the secondary 0–100% failure-rate axis to
  `view_time.py`.
- Colored elapsed-time points by execute machine.
- Added one axes-relative horizontal band per error type between 80% and 90% of the
  plot height. Error points use execute-machine fill color and error-type ring
  color; each band is labeled inside the right side of the plot rather than through
  an error legend.
- Added `execute_machine_name()` to execute-side `worker_misc.py`. The generic
  workflow writes this value into `individual_metadata.json`, and
  `runtime_identity()` includes it for simulator workflows.
- Changed `view all` to run the remaining cost and integrated time views.
- Updated generic/installed tests, agent guidance, architecture, terminology, and
  blueprints.

## Rationale

- Axes-relative band positions remain near the visual top regardless of elapsed-time
  units or range.
- A filled circle plus outer ring carries machine and error-type identity at the
  same event without a large centralized error legend.
- Execute-side sampling preserves the actual worker provenance and keeps submit-side
  ClassAds diagnostic rather than authoritative.

## Impact

- Users now inspect timing, failures, machines, and typed error occurrences with
  `yadof view time`.
- `yadof view all` produces cost and time images only.
- Existing records without execute-side identity render as `local` when explicitly
  marked local, otherwise `unknown`.

## Follow-Up

- Existing custom workflows should adopt
  `worker_misc.execute_machine_name()` in every lifecycle metadata write.
