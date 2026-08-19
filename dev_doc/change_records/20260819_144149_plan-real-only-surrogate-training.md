# 2026-08-19 14:41 - Plan Real-Only Surrogate Training

## Context

- The conditional-INR surrogate currently combines real rawData fitting with
  mixup, task-owned importance weights, weighted query sampling, rank-specific
  forced queries, and a secondary relative-loss branch.
- The user requested a follow-up plan that removes curve-specific adjustments and
  mixup, while ensuring the earlier method-package restructuring anticipates this
  direction.

## Change

- Added a manual toDo that may execute only after the modular surrogate/optimizer
  toDo is complete and archived.
- The plan defines a real-only, uniformly sampled, single-loss training contract;
  required code/config/API/checkpoint/documentation removals; preserved generic
  numerical mechanisms; legacy-checkpoint policy; staged implementation; and
  installed-wheel acceptance criteria.

## Rationale

- Recording the dependent work now prevents the preceding refactor from promoting
  temporary conditional-INR heuristics into stable cross-method contracts.
- Explicit removal and preservation lists make “simpler” testable without confusing
  task-specific training bias with necessary rawData, numerical, scheduling, or
  uncertainty contracts.

## Impact

- No package code, runtime behavior, public API, or current architecture changed.
- Future work is tracked by
  `dev_doc/toDo/20260819_144148_simplify-surrogate-real-only-training.md`.

## Follow-Up

- Complete and archive the modular-method toDo first. Execute this new manual toDo
  only after that prerequisite is satisfied.
