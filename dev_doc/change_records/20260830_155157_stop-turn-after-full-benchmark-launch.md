# 2026-08-30 15:51 - Stop The Agent Turn After Full Benchmark Launch

## Context

- A full-budget measured benchmark can run for several hours.
- The benchmark user guide prohibited polling Windows window registration, but it
  did not prohibit repeated `inspect` calls or keeping an AI-agent turn alive only
  to wait for completion. That gap could consume substantial tokens without making
  progress.

## Change

- Defined a successful detached full-budget launch receipt as the default agent
  handoff boundary.
- Instructed agents not to poll, wait, schedule recurring checks, or keep the
  current turn open solely to observe the benchmark.
- Allowed independent work to continue, while requiring the turn to end when no
  independent work remains or all remaining work depends on benchmark completion.
- Reserved later bounded inspection or ongoing monitoring for an explicit user
  request, while allowing immediate diagnosis of a failed or ambiguous launch.

## Rationale

- Detached execution already gives the benchmark an independent visible console
  and returns the paths needed for later inspection. Ending the agent turn after
  that handoff preserves those execution semantics while avoiding token-expensive
  polling during a potentially hours-long run.

## Impact

- Updated the benchmark user entry page and execution workflow.
- Updated the benchmark developer invariant and the repository terminology for a
  detached launch receipt.
- No runtime, workspace format, command behavior, or result format changed.

## Follow-Up

- None. A user can request a later one-time progress snapshot or explicitly ask for
  monitoring when that behavior is desired.
