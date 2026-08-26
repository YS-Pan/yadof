# 2026-08-26 15:02 - Render Benchmark Progress On The Foreground Thread

## Context

- A second full-scale run still showed an active cell at zero throughout optimize,
  followed by a brief 100 percent frame before the next cell reset to zero.
- The completed command log contained 2,020 valid per-evaluation yadof snapshots
  and the benchmark parser accepted all 2,020. The missing movement was therefore
  after parsing rather than in yadof evaluation or the snapshot grammar.
- The real runner invoked `CellProgress` and Rich directly from stdout/stderr drain
  threads. Existing tests invoked the same methods synchronously and did not cover
  the Windows terminal's thread ownership.

## Change

- Limited pipe-drain threads to separate append-only logging plus display-event
  enqueueing.
- Changed the foreground subprocess wait into a short bounded wait loop that
  services queued progress and optional streamed-output events while the child is
  running. Only that foreground thread now writes through or refreshes Rich.
- Added an actual subprocess/pipe regression proving early and cross-generation
  cumulative values render and every refresh occurs on the foreground owner
  thread.
- Updated benchmark operator, architecture, blueprint, and root integration
  documentation with the terminal-thread invariant.

## Rationale

Rich remains the only cursor manager, but the thread that owns the foreground
console now also owns every terminal operation. Logging stays concurrent so child
pipes cannot block, and the foreground loop remains responsive to timeout and
progress without polling workspace evidence.

## Impact

- New `run` and `resume` processes visibly advance cell progress during optimize on
  Windows rather than relying on undefined background-thread terminal behavior.
- Command logs, run identity, result evidence, ETA semantics, and yadof package code
  are unchanged.
- The focused output suite passes 18 tests and the complete benchmark automation
  suite passes 54 tests using fresh external pytest state.

## Follow-Up

- None.
