# C4 Components

## Planning and identity

- Path/config validation contains declared inputs below the benchmark root while
  allowing one explicit output root.
- `build_plan` expands suites, selectors, budgets, commands, prerequisites, and
  lower-bound evaluation/storage estimates without writing.
- Preflight validates baselines, installed package identity, strategies, resources,
  disk, and Python/CUDA facts without launching a simulator.
- Run creation fingerprints and snapshots configuration, runner modules, package,
  strategies, baselines, histories, host facts, and expanded cells. It also
  shallow-scans at most 64 immediate prior run directories and freezes at most 512
  completed-cell timing observations in `timing_history.json`.

## Execution and recovery

- Attempt materialization starts from the run-local baseline snapshot, applies
  runner configuration and strategy content, then seals input fingerprints.
- Logged execution writes started metadata first, drains stdout/stderr concurrently
  into separate append-only logs, queues timestamped parsed snapshots, and lets the
  foreground owner append command lifecycle/progress JSON lines to `progress.jsonl`.
  Finished metadata fingerprints all three streams after termination.
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
- When an `isatty()` stream inherits `TERM=dumb` or `TERM=unknown`, `CellProgress`
  removes that contradictory value only from its Rich `Console` environment. Rich
  can then execute live refreshes without mutating the runner or child environment.

## Status and ETA

- `inspect` combines atomic state with immutable plan data, the run-local bounded
  timing-history snapshot, completed attempt wall-clock durations, and only the
  active command's bounded progress-event tail. Older commands without the
  sidecar fall back to the bounded stderr tail.
- Cell estimates prefer the median of exact prior-run cell matches, current-run
  same-case/arm completions, compatible prior-run matches that omit implementation
  fingerprints, then current-run same-arm completions. Same-case evidence from a
  different arm and all-arm pooling are not point-estimate cohorts. Declared and
  plan-average evaluation lower bounds remain the final fallbacks.
- With at least three timestamped completed generation intervals, a robust
  non-negative Theil-Sen-style duration slope forecasts the remaining generation
  phases. This can raise, but not lower, the matched-cell remainder. Cumulative
  linear evaluation-rate projection is used only when that phase evidence is not
  yet available, and a running-cell recheck floor is retained.
- Output includes checked/start times, elapsed seconds, active phase/count/idle
  age, estimated remaining seconds/completion UTC, confidence, basis counts,
  support sample counts/relative MAD, generation timing, and a caveat. Timing is
  operational best effort, never scientific evidence.

## Collection and reporting

Collection consumes public recorded-data, cost-viewer, and surrogate-viewer
surfaces. It retains incomplete/invalid cells and aligns performance pairs only
when budgets and initial populations match. Reports expose raw/descriptive results,
validity, exclusions, and tool gaps without ranking algorithms.
