# 2026-08-13 16:56 - Document Loss-Tolerant Recording Intent

## Context

- A 5,000-candidate fast SAW campaign showed nearly constant simulator time but
  generation wall time increasing linearly with accumulated history.
- Fast recorded every completion synchronously, while local and distributed modes
  normally used population-batch recording. Both approaches still mutated and
  recopied campaign-wide history files.
- The desired future reliability policy explicitly permits missing candidate
  history but requires storage loss and corruption never to stop optimization.

## Change

- Added a manual toDo for replacing the current global JSONL/ZIP persistence path
  with one backend-neutral finalizer, direct current-cost calculation, bounded
  asynchronous best-effort recording, immutable per-candidate records, and an
  optional rebuildable index.
- Recorded the measured SAW failure shape, the intended failure-domain separation,
  old-format replacement policy, tolerant recovery behavior, implementation
  sequence, non-goals, and detailed acceptance criteria.

## Rationale

- Future implementation needs an explicit intent contract so a local fix for fast
  mode does not preserve the same history-size complexity in another backend.
- Making data loss acceptable changes the former evidence-first runtime contract;
  documenting that decision before implementation prevents persistence failures
  from continuing to masquerade as evaluation failures.

## Impact

- No runtime behavior, current architecture, user workflow, or storage format has
  changed yet.
- The new manual toDo becomes design input only when the user explicitly requests
  its implementation.

## Follow-Up

- Execute and retire the toDo only after the unified writer, loss-tolerant readers,
  documentation updates, and performance/failure tests satisfy its completion
  rule.
