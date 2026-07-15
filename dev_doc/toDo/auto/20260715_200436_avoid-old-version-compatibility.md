# Avoid Old-Version Compatibility Design

## Context
- Compatibility aliases, dual data formats, silent fallbacks, migration branches,
  and retained old entry points make the current code contract ambiguous.
- The project should implement one current design. Support for an older version is
  added only when the user explicitly requests a specific migration path.

## Goal
- Code encountered during normal in-scope work should use only the current API,
  data format, file layout, and execution path.
- New work must not add a compatibility layer for older project versions.

## Guidance
- When already editing code that contains an old-version alias, fallback input
  format, migration-only branch, dual writer, or retired entry point, remove it when
  the current task provides a safe replacement in the same scope.
- Do not search the repository solely for compatibility code and do not expand the
  current task to redesign unrelated modules.
- A relative-import fallback that lets the same current file run both as a package
  module and as a copied same-directory job file is an execution-location mechanism,
  not old-version compatibility.
- Failure isolation, optional dependencies, and support for multiple current
  backends are not old-version compatibility.
- If removing an encountered compatibility path would require a data migration or
  a user decision outside the current task, report it and leave it pending.

## Completion Rule
- Remove each safely replaceable old-version compatibility path encountered in
  files already in scope.
- Keep this automatic toDo active for other incidental occurrences until its
  obsolete rule archives it.
