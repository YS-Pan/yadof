# 2026-08-26 08:28 - Group Benchmark Visualizations By Baseline

## Context

The benchmark runner placed every measured cell attempt's postprocessor artifacts
in a separate directory. The formal performance matrix therefore produced eighteen
task-result directories, making the three baseline workspaces harder to review as
coherent groups.

## Change

- The runner now writes task-specific artifacts to one
  `visualizations/<baseline-id>/` directory per baseline workspace.
- Each postprocessor receives the collision-safe
  `<cell-id>__attempt-####__` filename prefix, so arms, seeds, and replacement
  attempts can share the baseline directory without overwriting evidence.
- Cost plots remain together under the global `visualizations/viewcost/` directory.
- Focused tests and current benchmark documentation now lock the three-directory
  layout of the configured performance matrix.

## Rationale

Baseline grouping matches how reviewers compare task-specific outputs while the
cell/attempt prefix preserves unambiguous provenance and immutable retry evidence.

## Impact

New benchmark runs use three baseline result directories for the current matrix
instead of eighteen cell result directories. Existing run evidence is unchanged.

## Follow-Up

None.
