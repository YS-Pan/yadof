# 2026-08-30 22:13 - Authorize one Goal for the explicit-optimization refactor

## Context

The staged explicit-optimization plan required a new user instruction after every
stage and treated GPSAF `gamma` as an approved removal. The user reversed both
planning decisions: one Goal may sequentially refine and execute every stage
without ordinary stage-end waiting, while `gamma` must remain unchanged. The user
delegated the remaining plan choices.

## Change

- Rewrote the overall plan around one durable Goal, one active implementation
  stage at a time, automatic stage-to-stage continuation, objective pause
  conditions, a live stage ledger, and a verifiable yadof 0.5.0 stop condition.
- Replaced the six-stage map with eight narrower stages: publication-before-cost,
  Dataset/CostTable, EvaluationHandle, surrogate fit/predict, search/select,
  workspace-program pilot, retained-capability migration, and final cutover/release.
- Renamed the former Stage 3--6 handoffs to match their revised responsibilities
  and added dedicated Stage 7 and Stage 8 TODOs.
- Strengthened Stage 1 with a bounded two-phase group-commit coordinator,
  replayable interpretation semantics, pre-change recording measurements, and
  structural throughput/batching/memory gates.
- Made Stage 2--8 predictive but explicitly authorized for in-place refinement and
  execution when the one Goal names every file; completing a normal stage now
  archives its TODO, updates the ledger, commits, and automatically continues.
- Moved EvaluationHandle before surrogate/program work, separated the program
  pilot from advanced-capability migration and legacy deletion, and reserved
  deletion/release for Stage 8 after consumer evidence.
- Required retention of GPSAF `gamma` in its factory, settings, validation,
  semantic identity, and diagnostics. No removal, deprecation, migration, or
  selection-math change is part of this refactor.
- Scoped the Goal's measured execution to one foreground, host-run fast synthetic
  smoke/measured benchmark per implementation stage; real simulators,
  full-budget local/distributed work, shared clusters, paid services, and user-data
  migration remain outside the authorization.

## Rationale

A single durable Goal is large enough to survive context compaction but still has
a concrete stopping condition. Serial implementation preserves evidence-driven
refinement without making user availability an ordinary scheduling dependency.
Putting lifecycle and identity primitives before the visible program prevents the
program API from being designed around hidden backend or surrogate assumptions.
Separating pilot, migration, and deletion makes capability retention independently
verifiable.

## Impact

Only developer planning documentation changed. No stage was executed, no source,
test, architecture, blueprint, terminology, user documentation, package resource,
installed wheel, benchmark workspace, simulator, or durable evidence changed.
Historical change records that document the earlier plan remain append-only.

The pre-change repository was clean at
`d5fb680bfdb74b318e1a23c781db08c5c3135124` on `main`, which was one commit ahead
of the then-known `origin/main`.

## Automatic TODO Check

The bounded in-scope check found no implementation occurrence to trigger. The
recording plan remains explicitly future-facing and does not misstate the current
cost-before-admission architecture; no component config key or second settings
entry was introduced; `0.5.0` is the real planned package version rather than an
incidental release marker; and no source/test file was touched for a redundancy
cleanup. All four recurring automatic TODOs therefore remain active and unchanged.

## Follow-Up

Start the refactor only with a Goal that explicitly names all eight active TODO
paths. At Goal start, freeze the current HEAD and TODO digests in the overall-plan
ledger, refine Stage 1 only as needed to account for newer repository evidence,
then follow the automatic serial loop. Any future change to GPSAF `gamma` requires
a separate user decision and handoff.
