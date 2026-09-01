# Continuously Remove Incidental Release Markers

## Context

- After an incompatible data-format or implementation-boundary change, module
  names, directory names, errors, and documentation can accumulate transitional
  labels such as “second edition.” Those labels communicate only that an earlier
  edition once existed. They do not describe the current component's
  responsibility, and they make a new workspace appear to require knowledge of a
  historical migration.
- Cleanup must not discard real capabilities, data-integrity validation, or the
  package's public version.

## Goal

- When normal work naturally reaches source, tests, active documentation, or a
  workspace explicitly selected by the user, remove wording, path layers, module
  suffixes, aliases, and compatibility wrappers that exist only to denote a later
  edition.
- Name current interfaces and layouts directly by responsibility so they read as
  native design, while preserving actual features, failure semantics, data
  integrity, and verifiable format boundaries.

## Guidance

- Inspect only files already in scope for the normal task, their direct callers,
  tests, active documentation, and the current diff. Do not scan unrelated parts
  of the repository solely for this toDo unless the user explicitly requests a
  complete cleanup.
- First establish that a match really is a yadof release-transition marker. Fixed
  markers in third-party formats, ordinary variable names, version fields required
  by a protocol itself, and the package's real public version are not cleanup
  targets.
- In particular, `YADOF_OPTIMIZATION_PROGRAM["api"] ==
  "yadof.optimize.program/v1"` is the exact executable protocol discriminator:
  planning and runtime accept it and reject lookalike unsupported values. It is
  not incidental release prose and must remain until the protocol contract itself
  is deliberately replaced.
- Rename transitional modules, directories, and fields directly by responsibility.
  Do not preserve old-name import aliases, dual-path readers, or old/new wording
  that continues to expose the transition.
- Remove a format or metadata version layer that exists only to number the current
  recorded-data layout. Do not reset the old number to `1`. A field that belongs to
  the contract of an independent external protocol or data type is outside this
  rule.
- Before migrating existing workspace data, confirm that no campaign is running,
  resolve exact source and destination paths, avoid overwrite conflicts, and verify
  record counts, readability, and evidence content before and after the migration.
  Without user authorization, report the required migration instead of rewriting
  user data.
- When behavior or layout changes, update directly related tests, architecture,
  blueprints, terminology, user documentation, and the change record, then follow
  the installed-package verification workflow.

## Completion Rule

- For one natural trigger, all in-scope design and markers confirmed to be purely
  transitional have been removed, real functionality and data remain intact, and
  tests plus data checks proportional to the risk have passed.
- This toDo is recurring. Keep it under `toDo/auto/` after one completed occurrence
  so future matching work can trigger it again.

## Obsolete Rule

persistent
