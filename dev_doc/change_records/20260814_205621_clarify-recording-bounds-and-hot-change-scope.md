# 2026-08-14 20:56 - Clarify Recording Bounds And Hot-Change Scope

## Context

- A fresh review of the loss-tolerant recording toDo found ambiguity around the
  16/32 candidate limits, large rawData, fingerprint invalidation, and shutdown of
  a writer thread blocked in filesystem I/O.
- The 16/32 values were tuning examples rather than a scientific or product
  boundary. Yadof tasks may also produce much larger candidates than the SAW
  workspace; a representative antenna pattern contains `10 * 360 * 360` floating-
  point values.
- Structural parameter/objective dimension changes require optimizer-state
  semantics beyond the recording project and are intentionally deferred.

## Change

- Recast 16 candidates per segment and 32 unpublished candidates as initial,
  campaign-frozen defaults under a general configurable bounded-loss contract.
- Separated the normal segment byte target, maximum single-candidate reservation,
  and total unpublished byte budget. Large candidates that exceed the normal target
  may publish as singleton segments, while peak source/encoding ownership is
  included in byte accounting.
- Added float32/float64 antenna-pattern sizing to the planned benchmarks and made
  whole-generation loss a best-effort minimization goal rather than an impossible
  absolute guarantee.
- Defined bounded writer shutdown as a bound on caller wait, not thread
  cancellation. A blocked in-flight publication has unknown outcome; a long-lived
  process retains the workspace lock until the writer exits, while a CLI process
  may terminate because the writer is daemonized.
- Split interpretation, evaluation, and complete task-snapshot fingerprints so an
  execution-only source edit does not force historical cost recalculation.
- Froze recorder infrastructure configuration per campaign while retaining
  generation-boundary task-semantic reload.
- Scoped supported in-campaign task correction to stable parameter identity/count
  and objective count, and aligned architecture, blueprints, and user guidance with
  that limitation.
- Clarified that the segment reader ignores legacy global-ZIP/JSONL history and never
  migrates, deletes, or rewrites it.

## Rationale

- Runtime queues need enforceable limits, but no particular adjacent candidate
  counts form a meaningful acceptability threshold. Parameterized limits preserve
  bounded memory and loss exposure without overfitting policy to 16 or 32.
- Count limits do not protect memory when one task result is several MiB. Distinct
  byte targets and hard reservations support both small SAW records and large field
  arrays without discarding every candidate above a batching target.
- Python cannot safely kill a thread blocked inside an operating-system filesystem
  call. Precise lifecycle wording prevents the implementation from claiming an
  impossible guarantee.
- Shape-preserving task edits retain yadof's user-trusted flexibility while keeping
  optimizer dimension migration out of a persistence-performance project.

## Impact

- No runtime code, installed package behavior, or history format changed.
- The active toDo now has implementable shutdown, cache invalidation, byte-budget,
  legacy-history, and task-mutability acceptance rules.
- Current architecture and user workflow documentation no longer promise
  in-campaign parameter-schema or objective-width migration.

## Follow-Up

- Implement the active recording toDo only when explicitly requested.
- Create a separate future toDo if in-campaign parameter identity/count or
  objective-count changes become required.
- During implementation, benchmark peak resident and encoded size for both
  SAW-shaped records and the representative antenna-pattern payload before choosing
  shipped byte defaults.
