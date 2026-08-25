# 2026-08-25 09:01 - Benchmark Rich Progress And Visualization Layout

## Context

- The benchmark runner manually erased and redrew one cell-level terminal line.
  Lifecycle and streamed output could leave old progress text visible, especially
  when stdout and stderr were interleaved.
- Long cells exposed only global cell completion, so users could not see the
  individual-evaluation progress inside the active cell.
- Every postprocessor artifact and cost view used prefixes in one flat
  `visualizations/` directory, which made human inspection inconvenient.

## Change

- Replaced the manual terminal-control implementation with a Rich live-progress
  region. The active cell's evaluation task is inserted above the global cell
  task, while lifecycle and streamed messages are printed above both tasks.
- Enabled yadof's piped per-generation progress for benchmark optimization
  commands, retained every original snapshot in command logs, and converted the
  snapshots into the active cell task. Redirected benchmark output emits
  percentage-throttled complete snapshots.
- Added a `benchmark` optional dependency extra for Rich and included Rich in the
  development extra.
- Changed output layout so each measured attempt owns
  `visualizations/<cell-id>__attempt-####/`, while all prefixed cost views share
  `visualizations/viewcost/`.
- Updated runner tests, operator/agent guidance, architecture, blueprint,
  terminology, and baseline overview documentation. Frozen baseline contents and
  existing generated runs remain unchanged.

## Rationale

- Rich owns cursor movement, live-region clearing, message coordination, and task
  ordering, avoiding another custom terminal renderer. A small ASCII Rich column
  preserves compatibility with the workspace's Windows GBK console while Rich
  continues to own the live display.
- Child progress snapshots are already the authoritative per-individual outcome
  stream; converting them avoids polling mutable history or inventing a parallel
  progress source.
- Separate result directories remove cross-cell visual clutter. Keeping cost plots
  together preserves quick algorithm/case comparison.

## Impact

- `benchmark run` and `resume` now require the `benchmark` extra and show two
  ordered interactive progress tasks while a cell is active.
- New attempts use the categorized visualization layout. Old run directories are
  not migrated and remain readable as immutable evidence.
- No simulator, optimizer, recorded-data, report schema, or frozen scientific
  input changed.

## Follow-Up

- None.
