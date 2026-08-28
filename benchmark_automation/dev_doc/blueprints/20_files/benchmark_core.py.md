# File Blueprint: benchmark_core.py

## Intent

Provide a temporary, no-policy compatibility facade over `benchmark_runtime` for
the CLI and current tests/callers. The file remains below 250 physical lines.

## Responsibilities

- Import and re-export the stable current call surface from owned runtime modules.
- Load an existing run's execution module from
  `inputs/execution/benchmark_runtime` under a unique package name.
- Translate the snapshotted runtime's `BenchmarkError` into the current facade
  error type without falling back to live execution code.

Planning, storage, state, subprocess, collection, report, progress, and ETA logic
do not belong here.

## Invariants easy to lose

- Progress lines are logged even when consumed for the live display.
- Parsed progress is also retained as foreground-written timestamped JSONL between
  command lifecycle events; finished metadata fingerprints that sidecar.
- Stdout/stderr drain concurrently and remain separate on disk.
- Drain threads enqueue terminal events; the foreground child-wait loop alone calls
  Rich so Windows console cursor rendering never originates on a pipe thread.
- A Rich event renders only after both cell/global tasks hold coherent state.
- A true TTY cannot remain classified by Rich as dumb solely because its launcher
  exported `TERM=dumb`/`unknown`; normalize only the console-local environment.
- A positive large-cell count is visibly nonzero.
- New-run creation is delegated to `benchmark_runtime.state`, which copies the
  complete execution package and all selected input snapshots.
- ETA never pools another arm merely because its case matches. Exact/compatible
  matched-cell medians precede current same-arm and declared lower bounds; active
  generation trends require at least three complete timestamped intervals.
- Run inspection never writes or waits.
- Immutable artifacts use create-new; only documented latest views use atomic
  replacement.
- Collection uses public yadof surfaces and retains validity/exclusion context.

## Compatibility boundary

Private aliases exist only for current facade callers. Active runtime modules use
public sibling service names. Current source/package/artifact digests are never
compared to decide resume or historical completion.
