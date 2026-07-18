# 2026-07-18 13:33 - Package Workspace Init And Check CLI

## Context

- The installed workspace/config/task-loading foundation had no safe command for a
  user to create or diagnose the minimum user-owned workspace.
- Package conversion step 3 required a neutral starter, portable provenance,
  idempotent no-overwrite behavior, read-only diagnostics, and wheel-installed
  verification outside the repository.

## Change

- Added a versioned bundled generic template, strict portable
  `.yadof/workspace.json` marker, staged validation, exclusive/marker-last publish,
  and attempt-scoped rollback.
- Added `yadof init [PATH]`, which initializes or confirms a workspace without
  overwriting, repairing, upgrading, or deleting user content.
- Added `yadof check [--workspace PATH]`, which reports structure, provenance,
  config/task contracts, workflow syntax, static rawData, and selected backend
  prerequisites without executing workflow or invoking/installing external tools.
- Added focused unit/failure tests and expanded artifact verification to run
  init/check from an installed wheel outside the repository while site-packages is
  non-writable.
- Updated architecture, blueprint, terminology, user, repository, and contributor
  documentation for the new boundary.

## Rationale

- Treating the marker as a commit record and publishing it last prevents partial
  workspaces from appearing complete. Exclusive creation plus precise rollback
  protects both pre-existing and concurrently created user files.
- Reusing normal config/task/rawData validators keeps init/check aligned with future
  runtime behavior, while AST-only workflow checking preserves the strict
  no-expensive-evaluation boundary.
- A generic task demonstrates the contract without coupling package defaults to a
  simulator, vendor, model, adapter, concrete active variables/objectives, or
  physical result.

## Impact

- Installed users can prepare and diagnose package-era workspaces before evaluation
  and optimization commands migrate.
- Runtime evaluation remains under `project/`; init/check do not claim that later
  package stages are complete.
- Template and marker schema versions are now compatibility boundaries and existing
  initialized workspaces are never automatically upgraded.

## Follow-Up

- Package step 4 may build local evaluation on the same explicit workspace/config/
  task contracts. It must remain a separately triggered task.
