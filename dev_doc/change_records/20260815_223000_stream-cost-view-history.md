# 2026-08-15 22:30 - Stream Cost-View History

## Context

- `view cost` independently scanned the segment catalog for diagnostics, dynamic
  history, and record annotations. It reopened every candidate ZIP member for the
  historical cost path and freshly loaded parameter/cost task modules per record.
- Cumulative hypervolume repeatedly supplied the full prior history to the HV
  indicator even when most points were dominated.

## Change

- Added a frozen historical rawData snapshot that captures finalized segment names
  once and streams each segment through one open ZIP for manifest checks, rawData
  decode/schema validation, and candidate diagnostics.
- Changed the cost viewer to use that sole streamed path, retain direct record
  provenance, and use one frozen parameter/`calc_cost.py` interpreter while it
  processes all segment batches. The command passes captured objective names to its
  report and renderer instead of reopening `calc_cost.py`.
- Maintained a cumulative nondominated front before each all-history HV call; the
  current-generation HV call also receives its nondominated subset.

## Rationale

- Immutable finalized segments make a command-local path snapshot coherent without
  copying history. Combining the previously separate passes eliminates repeated
  ZIP opens, rawData decoding/validation, catalog traversal, and task-module loads
  while retaining per-candidate failure isolation.
- Dominated minimization points cannot change hypervolume, so excluding them
  preserves the displayed series while reducing cumulative work.

## Impact

- `yadof view cost` has one default execution path and adds no verification or HV
  disablement mode. Its progress is bounded by frozen segment count.
- New regression coverage verifies snapshot exclusion of later segments, one open
  per segment, frozen task interpretation, and Pareto-only HV inputs. Developer and
  user documentation describe the command-local freeze boundary.
