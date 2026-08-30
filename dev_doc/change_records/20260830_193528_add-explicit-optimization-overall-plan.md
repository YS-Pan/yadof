# 2026-08-30 19:35 - Add explicit-optimization overall plan context

## Context

The generated explicit-optimization Goal had accumulated cross-stage reliability,
compatibility, example-delivery, workflow, and benchmark details. The user asked
for a shorter Goal that can recover those details from a dedicated overall plan
after context compaction.

## Change

- Added a time-named `dev_doc/context/` document for the explicit-optimization
  refactor's outcome, invariants, stage map, rolling decision loop, benchmark
  policy, and final completion criteria.
- Linked the plan to all six active stage TODOs and kept their individual scope and
  execution authority in `dev_doc/toDo/`.
- Distinguished the context document from current architecture, an executable
  TODO, and user authorization so it cannot become a second task queue.
- Recorded that a compact Goal should state the framework outcome and key retained
  boundary, then refer to the overall plan and stage TODOs for details.

## Rationale

A filename-targeted context document gives later sessions one bounded source to
reload after compaction while keeping the Goal short. The mandatory timestamped
context filename preserves repository discovery and expiry semantics; the document
title supplies the requested “Overall Plan” identity.

## Impact

Only developer planning documentation changed. No active TODO was executed or
made authoritative beyond its current status, and no source, tests, package
resources, user documentation, installed wheel, or benchmark artifacts changed.

## Follow-Up

Future Goal text should link to the overall-plan context. Stage 1 remains the only
exact TODO and still requires explicit user authorization before implementation.
