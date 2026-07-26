# 2026-07-24 18:59 - Add Error And All Views

## Context

- Failure-rate calculation and rendering lived inside the elapsed-time view, which
  mixed runtime performance with failure diagnosis.
- Users needed to see when each error occurred, distinguish error types visually,
  and run all available views with one command.

## Change

- Added `yadof.tools.view_error`, which reads all recorded evaluation rows,
  reports failure rate, classifies error types, lists every occurrence time, and
  plots categorical error events with distinct colors plus a smoothed failure-rate
  axis.
- Removed failure-rate summary and plotting from `view_time`.
- Added `yadof view error` and `yadof view all`; the grouped command prints labeled
  cost/time/error summaries and creates three images with one shared timestamp.
- Added focused error-view, CLI, artifact, and grouped-view tests.
- Updated agent documentation, architecture, blueprints, and the project overview.

## Rationale

- A categorical error-type axis preserves individual occurrence times without
  merging unrelated failures, while color provides a second, immediately visible
  type encoding.
- Calculating failure rate from every usable evaluation record preserves the
  original denominator and permits zero-error histories.
- Keeping `view all` as CLI orchestration reuses the three Python tool APIs and
  avoids a second implementation of their summaries or plots.

## Impact

- `view time` no longer displays failure rate; use `view error` for failure
  diagnostics.
- Normal individual views still support custom output paths and summary-only mode.
  `view all` uses the three standard default names and can suppress all images with
  `--summary-only`.

## Follow-Up

- None.
