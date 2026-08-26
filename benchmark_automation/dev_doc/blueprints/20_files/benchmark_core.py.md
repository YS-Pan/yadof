# File Blueprint: benchmark_core.py

## Why this file is exceptional

The core is intentionally one testable orchestration module, but it crosses many
contracts: identity, filesystem publication, subprocess streams, progress, ETA,
collection, and reporting. Recreating it requires preserving section boundaries
and dependency direction rather than splitting stateful behavior arbitrarily.

## Expected section order

1. Imports, constants, errors, path types, Rich/progress parsing.
2. Canonical JSON/hash/path/file helpers and configuration loading.
3. Planning, preflight, package/resource fingerprints, and run creation/loading.
4. State/attempt/snapshot/materialization helpers.
5. Logged subprocess execution, cell execution, progress, resume.
6. Public-yadof collection and metric/report transformations.
7. Bounded summaries, read-only timing estimation, inspect.

## Invariants easy to lose

- Progress lines are logged even when consumed for the live display.
- Stdout/stderr drain concurrently and remain separate on disk.
- Drain threads enqueue terminal events; the foreground child-wait loop alone calls
  Rich so Windows console cursor rendering never originates on a pipe thread.
- A Rich event renders only after both cell/global tasks hold coherent state.
- A true TTY cannot remain classified by Rich as dumb solely because its launcher
  exported `TERM=dumb`/`unknown`; normalize only the console-local environment.
- A positive large-cell count is visibly nonzero.
- ETA reads at most the active command's bounded tail; completed-cell duration uses
  state timestamps rather than successful log scanning.
- Run inspection never writes or waits.
- Immutable artifacts use create-new; only documented latest views use atomic
  replacement.
- Collection uses public yadof surfaces and retains validity/exclusion context.

## Refactoring boundary

Extract a module only when it gains a stable independent contract and reduces
coupling without duplicating JSON/state/path helpers. Do not add wrappers merely to
shorten this file or keep compatibility with an obsolete internal name.
