# 2026-08-18 17:36 - Plan Modular Surrogate And Optimize Methods

## Context

- The current surrogate and optimizer packages each contain one concrete method at
  the package root, which makes the ownership boundary for future methods unclear.
- The requested work was to produce an implementation plan rather than change the
  runtime code.

## Change

- Added a manual toDo for moving conditional INR and GPSAF + GA/NSGA-III into
  method-specific subpackages.
- The plan defines parent-package common responsibilities, method contracts and
  registries, configuration/lifecycle decisions, checkpoint compatibility,
  viewer/history integration, migration phases, verification, and completion
  criteria.

## Rationale

- A staged plan is needed because public APIs, campaign state, checkpoint recovery,
  scheduler state, and the surrogate viewer currently cross the proposed directory
  boundary.
- Separating stable orchestration from method-owned numerical code avoids copying
  infrastructure when a second real method is added.

## Impact

- No package code, runtime behavior, public API, or current architecture changed.
- Future implementation work is tracked by
  `dev_doc/toDo/20260818_173629_modular-surrogate-optimize-methods.md`.

## Follow-Up

- Execute the manual toDo only when explicitly requested, then archive it after all
  code, tests, documentation, installation, and compatibility criteria pass.
