# 2026-08-30 18:05 - Staged explicit-optimization TODOs

## Context

- The user requested that the broad explicit-optimization architecture proposal be
  divided into a sequential TODO series. Only the first stage may be exact; each
  later stage must remain predictive until the preceding stage has been validated
  and reviewed with the user.
- The user then explicitly paused implementation and requested a TODO-only outcome.

## Change

- Added six manual TODOs under `dev_doc/toDo/` covering evidence preservation,
  dataset/cost tables, explicit surrogate fit/predict, search/selection primitives,
  workspace-owned optimization programs, and final evaluation/release convergence.
- Refined stage 1 into the only executable specification. Stages 2--6 explicitly
  require later refinement and renewed user direction.
- Each stage requires a full `test-com/synthetic-antenna` validation using NSGA-III,
  a simple surrogate, population 100, 20 generations, and one fixed seed after its
  own focused and installed-package checks.

## Rationale

- The sequence creates a user review boundary after every independently validated
  change and avoids freezing downstream APIs before upstream evidence is available.

## Impact

- No package code, tests, architecture, blueprint, terminology, user contract, or
  public behavior changed. A temporary implementation spike and its installed wheel
  were fully reverted before this record.

## Follow-Up

- Execute stage 1 only after the user explicitly requests that specific TODO. After
  reporting its tests and benchmark result, use the user's response to replace the
  predictive stage-2 draft with the next exact TODO.
