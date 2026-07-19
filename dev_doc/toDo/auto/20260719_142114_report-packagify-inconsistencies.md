# Report And Correct Packagify Inconsistencies

## Context

- Converting the project into an installable package changed source paths, runtime
  ownership, documentation locations, naming, and package/workspace boundaries.
- Stale assumptions from before or during packagify may remain and can make current
  code, tests, or documentation disagree with the packaged design.

## Goal

- Report every packagify-related inconsistency encountered during normal in-scope
  work.
- Correct simple, safe inconsistencies in the same scope.
- Report difficult or risky inconsistencies without changing them.

## Guidance

- Trigger this toDo only when normal work naturally exposes a mismatch caused by
  packagify; do not search the repository solely for occurrences.
- A simple inconsistency has one clear current replacement and can be corrected
  locally without changing public behavior, data, APIs, or architecture. Examples
  include stale paths, directory names, links, and wording.
- A difficult inconsistency requires design judgment, broad refactoring, migration,
  external-system validation, or a user decision. Leave it unchanged.
- In the current response, report the file or area, the mismatch, and whether it was
  fixed. For a difficult issue, also state why it was not changed.
- Do not add old-version compatibility merely to preserve a pre-package path or
  behavior.

## Completion Rule

- Fix and report each simple matching issue encountered in the current scope.
- Report but do not fix each difficult matching issue.
- Keep this automatic toDo active for future incidental occurrences.

## Obsolete Rule

manual
