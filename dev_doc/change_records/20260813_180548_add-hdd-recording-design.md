# 2026-08-13 18:05 - Add HDD-Aware Recording Design

## Context

- The loss-tolerant recording toDo originally selected one immutable filesystem
  file per candidate after removing the campaign-wide ZIP/JSONL rewrite.
- That layout isolates failures but still creates small-file, directory-update,
  seek, and durability-flush overhead on rotational disks.
- The requested design must remain common to fast, local, and distributed modes and
  may lose bounded recent data without allowing storage failure to stop optimization.

## Change

- Revised the future recording design to keep one logical independently checksummed
  candidate frame while packing bounded groups into immutable sequential segments.
- Added a single workspace writer, byte/count/time flush thresholds, large buffered
  sequential writes, no per-candidate durability flush or index transaction,
  deferred rebuildable indexes, no online compaction, and bounded HDD read/write
  contention rules.
- Added HDD-oriented performance estimates, loss-domain semantics, suggested
  starting thresholds, and deterministic verification requirements that do not
  require a physical HDD in the default test suite.

## Rationale

- A queue alone overlaps simulation and persistence but does not increase device
  throughput. Sequential immutable micro-batches remove historical rewrite work and
  amortize the seeks and metadata operations that dominate small writes on HDDs.
- Independent frames preserve candidate-level corruption isolation when a segment
  remains readable, while atomic segment publication confines incomplete writes to
  one explicitly bounded, acceptable loss unit.

## Impact

- No runtime behavior, current storage format, architecture, user workflow, or API
  changed; the manual toDo remains future design input.
- The implementation completion rule now requires a common serial segment writer
  and HDD-shaped performance/failure tests instead of one physical file per
  candidate.

## Follow-Up

- Benchmark the proposed 4--32 MiB, 32--256 candidate, and 0.2--1.0 second ranges
  during implementation and select bounded portable defaults from measured
  workloads rather than storage-model heuristics.
