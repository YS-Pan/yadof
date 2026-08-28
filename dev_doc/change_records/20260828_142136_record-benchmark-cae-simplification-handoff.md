# 2026-08-28 14:21 - Record benchmark and CAE simplification handoff

## Context

A concurrent read-only structure review quantified the size, duplication, and
private coupling in the benchmark runner and hierarchical-CAE implementation. Its
new manual toDo appeared coherently in the shared checkout while the qNEHVI
subpackage change was in progress.

## Change

- Added the manual handoff
  `dev_doc/toDo/20260828_140724_simplify-benchmark-and-hierarchical-cae-structure.md`.
- Preserved its distinction between byte-frozen historical experiment runners and
  future active runtime/package cleanup.
- Did not execute the plan, modify frozen evidence, or run a simulator or benchmark
  campaign.

## Rationale

Keeping the measured findings and phased acceptance rules in a standalone active
toDo lets a later explicitly authorized task simplify maintainable code without
mistaking frozen evidence footprint for removable active implementation.

## Impact

There is no runtime or user-workflow behavior change. The handoff remains manual
and requires explicit user selection before implementation.
