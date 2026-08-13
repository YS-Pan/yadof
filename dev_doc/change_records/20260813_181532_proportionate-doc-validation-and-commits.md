# 2026-08-13 18:15 - Use Proportionate Documentation Validation And Commits

## Context

- The development workflow required a wheel rebuild, reinstall, import-origin
  verification, full pytest run, change record, and commit for every documentation-
  only edit, regardless of its scope.
- Software tests add little evidence for a prose-only correction, and forcing a
  second change-record file plus commit makes tiny wording fixes unnecessarily
  expensive.

## Change

- Exempted content-only documentation edits from the installed-wheel/pytest cycle
  unless documentation packaging, discovery, command routing, generation, or
  executable examples are affected.
- Kept proportional UTF-8, diff, whitespace, link, path, example, and cross-
  reference checks for documentation edits.
- Added a narrow change-record/commit exception for localized corrections to
  exactly one existing documentation file when no contract, workflow, current-view
  document, toDo state, user instruction, public behavior, or historical decision
  changes.
- Updated the development guide, current development architecture, documentation
  blueprint, toDo lifecycle, and change-record contract to state the same boundary.

## Rationale

- Validation should target the behavior that changed. Prose-only edits do not
  justify executing the complete software suite, while packaging or executable
  documentation changes still need focused verification.
- File count alone cannot make a documentation change trivial: a one-file contract
  change may be important. The additional semantic limits preserve reviewable
  history while allowing genuinely minor corrections to remain uncommitted.

## Impact

- Future small documentation corrections may finish with a reported uncommitted
  one-file diff and no change record or pytest run.
- Substantive documentation work, including this governance change, still requires
  coordinated current-view updates, a change record, and a Git commit.
- Code/build/resource changes retain the installed-wheel full-test workflow.

## Follow-Up

- Apply the exception conservatively; when any criterion is uncertain, use the
  normal change-record and commit path.
