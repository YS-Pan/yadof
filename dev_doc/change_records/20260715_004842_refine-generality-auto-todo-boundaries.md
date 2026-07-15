# 2026-07-15 00:48 - Refine Generality Auto-ToDo Boundaries

## Context
- The generality auto toDo did not distinguish between documentation corrections
  and code findings.
- Its scope also needed to cover task-specific filenames and define exactly which
  code files may contain task- or software-specific content.

## Change
- Made matching documentation issues directly correctable by the automatic toDo.
- Prohibited automatic code edits and required code violations to be reported in
  text instead.
- Added task agnosticism and prohibited concrete task filenames in documentation
  while retaining `.aedt` and placeholder examples.
- Defined the four permitted task/software-specific code files under
  `project/job_template/`.

## Rationale
- Documentation wording is safe to repair opportunistically, while code coupling
  can affect runtime behavior and should be surfaced for deliberate follow-up.
- An exact allowlist makes the intended generic-code boundary auditable without
  confusing legitimate task files with framework coupling.

## Impact
- Updated only the active generality auto toDo; the trigger and obsolete contracts
  are unchanged.

## Follow-Up
- Code findings outside the allowlist will be reported when normal work encounters
  them; this change does not authorize a dedicated repository search.
