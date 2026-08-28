# Remove resolved benchmark tool-gap note

## Context

The benchmark retained a standalone `tool_gaps/` note for a surrogate-viewer
failure that was fixed, verified, committed, and pushed on 2026-08-23. The current
benchmark README already records that successful repair and its structural
acceptance runs, while the root change history preserves the implementation
decision.

## Change

- Removed the resolved surrogate-viewer tool-gap note and its now-empty tracked
  directory.
- Removed the stale operator link and changed the benchmark architecture guidance
  so unresolved observation gaps stay in bounded report output and become root
  `dev_doc/toDo/` handoffs only when implementation work remains.
- Corrected the compatibility architecture table to describe `benchmark_core.py`
  as the facade over `benchmark_runtime/`.

## Rationale

A resolved issue note duplicated current operator status and append-only change
history while making `tool_gaps/` look like an active benchmark lifecycle store.
The report's `tool_gaps` field remains the correct per-run disclosure surface;
repository-wide pending work and completed history already have authoritative root
locations.

## Impact

No runner code, report JSON field, benchmark input, generated run, preregistration,
history-snapshot capability, or verification evidence changed. Existing reports
that contain `tool_gaps` remain valid.

## Follow-Up

None.
