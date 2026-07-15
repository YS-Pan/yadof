# 2026-07-15 00:32 - Clarify Automatic Obsoletion And Add Generality ToDo

## Context
- The first automatic-toDo contract described time, validity, and manual handling
  in a way that could be read as three mutually exclusive policies.
- Yadof's documentation can also accumulate incidental wording that overstates the
  role of a current HFSS or Ansys example.

## Change
- Clarified that automatic toDos have two obsolete policies: the default automatic
  policy and an explicit manual policy.
- Under the automatic policy, the time and validity conditions are combined with
  OR: either an exceeded time limit or invalidating project changes archives the
  toDo. The default time limit remains seven days.
- Added an automatic toDo for correcting misleading, non-general documentation
  wording when normal work happens to expose it.

## Rationale
- The OR relationship ensures stale guidance is retired promptly for either reason
  without requiring a document author to choose between age and validity checks.
- An opportunistic toDo fits wording defects whose locations are unknown and whose
  value does not justify a dedicated repository-wide review.

## Impact
- Updated the toDo contract in `dev_doc/README.md`, architecture, blueprints,
  terminology, and the original trigger-types change record.
- Added `dev_doc/toDo/auto/20260715_003252_preserve-yadof-generality-in-docs.md`.

## Follow-Up
- The new automatic toDo uses the default automatic obsolete policy.
