# 2026-08-22 11:41 - Archive Real-Only Surrogate ToDo

## Context

- The real-only surrogate implementation, documentation, installed-wheel checks,
  and independent review were complete, but its manual toDo still treated a
  pre-refactor benchmark as a completion gate.
- The user plans to execute the modular surrogate/optimize and workspace submit-side
  composition toDos next. Those changes alter package, component, strategy,
  snapshot, state, and workspace boundaries, so measurements taken before them
  would need to be repeated and would not provide durable acceptance evidence.

## Change

- Removed benchmark selection, protocol, metrics, thresholds, execution budget,
  tradeoff, plan, verification, and completion-gate content from the real-only
  surrogate toDo.
- Recast that handoff around its completed implementation and verification scope,
  then moved it from `dev_doc/toDo/` to `dev_doc/obsolete/`.
- Updated both coordinated active toDos to depend on the archived implementation
  contract rather than a pre-refactor performance gate.
- Recorded that any later quantitative performance acceptance must be designed and
  executed against the final post-refactor architecture.

## Rationale

- Archiving now accurately reflects the completed simplification work while
  avoiding an expensive acceptance run whose result would immediately become stale.
- Keeping future performance criteria out of the archived handoff prevents the two
  structural tasks from being blocked by evidence that cannot validate their final
  design.

## Impact

- No package code, workspace task source, configuration, history, checkpoints, or
  runtime artifacts changed.
- No simulator, surrogate training, optimization, or HTCondor execution was started.
- The two coordinated manual toDos remain active and own the next implementation
  work; they must preserve the archived real-only and state-safety contracts.
