# C4 Components

## Planning and identity

- Path/config validation contains declared inputs below the benchmark root while
  allowing one explicit output root.
- `build_plan` expands suites, selectors, budgets, commands, prerequisites, and
  lower-bound evaluation/storage estimates without writing.
- Preflight validates baselines, installed package identity, strategies, resources,
  disk, and Python/CUDA facts without launching a simulator.
- Run creation fingerprints and snapshots configuration, runner modules, package,
  strategies, baselines, histories, host facts, and expanded cells.

## Execution and recovery

- Attempt materialization starts from the run-local baseline snapshot, applies
  runner configuration and strategy content, then seals input fingerprints.
- Logged execution writes started metadata first, drains stdout/stderr concurrently
  into separate append-only logs, and writes finished metadata after termination.
- State publication uses atomic replacement. Completed cells are skipped on resume;
  interrupted in-generation work receives a linked replacement attempt.
- Postprocessing and cost-view rendering are required measured-attempt stages.

## Progress rendering

- `_parse_yadof_progress` is the single parser for complete piped yadof snapshots.
- Stream-drain threads write their own append-only logs and enqueue display events;
  they never call Rich. The foreground subprocess-wait loop drains that queue and
  owns all terminal writes and refreshes.
- `CellProgress` converts per-generation counts to cumulative whole-cell counts.
- Any positive count lights at least one ASCII bar cell; values below ten percent
  retain one decimal so a 2,000-evaluation cell cannot look unchanged at `1/2000`.
- A compact task-owned text field carries count, unit, percentage, generation, and
  outcomes. The global line carries complete finished/total, ok/error/skip counts.
  There is no fixed 25-character detail cap.
- Rich automatic refresh is off. Both tasks update before one explicit refresh;
  lifecycle lines print above the live region.

## Status and ETA

- `inspect` combines atomic state with immutable plan data, completed attempt
  wall-clock durations, and only the active command's last bounded stderr tail.
- Pending-cell estimates prefer median scaled duration from the same case/arm,
  then same case, same arm, all completed cells, declared evaluation lower bound,
  and finally the plan-average lower bound.
- Active optimize progress projects its remaining evaluation time from elapsed
  command time and cumulative completed evaluations; the estimate never drops
  below the cohort remainder or a short recheck floor while the cell is running.
- Output includes checked/start times, elapsed seconds, active phase/count/idle
  age, estimated remaining seconds/completion UTC, confidence, basis counts, and a
  caveat. Timing is operational best effort, never immutable evidence.

## Collection and reporting

Collection consumes public recorded-data, cost-viewer, and surrogate-viewer
surfaces. It retains incomplete/invalid cells and aligns performance pairs only
when budgets and initial populations match. Reports expose raw/descriptive results,
validity, exclusions, and tool gaps without ranking algorithms.
