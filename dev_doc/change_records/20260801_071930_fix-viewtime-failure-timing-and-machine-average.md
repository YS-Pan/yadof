# 2026-08-01 07:19 - Fix ViewTime Failure Timing And Machine Average

## Context

- In a single-machine distributed workspace, the global completed-time average was
  9.39 minutes while the same machine's legend average was 6.85 minutes.
- The local failure-rate curve also formed approximately 90% spikes at generation
  boundaries even when the generation-wide rate was much lower.
- Failed rows can keep execution timing only in nested job metadata. ViewTime read
  start/end fields only from the top-level record, so those rows fell back to the
  common generation-batch `recorded_at` timestamp and a zero elapsed duration.

## Change

- Resolve start/end timestamps from both the individual record and nested job
  metadata, preferring workflow or Condor execution starts over runner/submission
  fallbacks and batch publication time.
- Recognize `condor_execution_elapsed_sec` as explicit duration evidence.
- Calculate each execute-machine legend average from completed evaluations only;
  failure-only machines remain represented as `avg. n/a`.
- Added focused regression coverage for nested timeout timing, batch-boundary
  ordering, explicit Condor elapsed time, and completed-only machine averages.
- Updated current user guidance and tools blueprints.

## Rationale

- Batch publication time describes persistence, not when an evaluation ran. Using
  it as the primary failed-row x coordinate moves failures to generation boundaries
  and creates a visualization artifact.
- Failed or timed-out durations are diagnostics rather than completed simulation
  times, so they must not lower or otherwise bias a machine's average-time label.

## Impact

- `yadof view time` places failed rows using their best recorded execution timing,
  produces failure-rate trends without batch-boundary clustering when that evidence
  exists, and aligns per-machine averages with the global completed-time average.
- Recorded evidence, optimization behavior, command signatures, and plot styling
  are unchanged.

## Follow-Up

- None.
