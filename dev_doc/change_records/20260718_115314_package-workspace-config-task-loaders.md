# 2026-07-18 11:53 - Package Workspace, Config, And Task Loaders

## Context
- The installable package/resource foundation existed, but task/config/runtime paths
  still belonged implicitly to the source `project/` tree.
- Package conversion step 2 required a stable writable-workspace boundary before
  CLI initialization, evaluation, persistence, optimizer, and tool migrations.

## Change
- Added immutable `WorkspaceContext` paths for root `config.py`, task input,
  jobs, recorded data, surrogate checkpoints, logs, and tool output. Relative path
  values resolve from the selected workspace and construction performs no writes.
- Added immutable package defaults plus isolated workspace-config loading, validation
  of names/types/modes/resources/task paths, source precedence reporting, and
  non-mutating temporary overrides.
- Added a source-fresh task loader that supports workspace-local absolute and
  relative imports through temporary namespaces without changing `sys.path` or
  retaining workspace modules in global import caches.
- Added installed `yadof.job_template` framework support: `Parameter`, normalization
  and assigned snapshot materialization, rawData validation/views, generic cost
  helpers, and workspace-explicit parameter/objective/cost APIs.
- Added focused two-workspace/config/task tests and extended wheel/read-only clean
  installation checks to cover the new installed modules and writable-path boundary.
- Updated current architecture, project/config/job-template/test blueprints, user
  transition documents, root/project/test entry documents, and terminology.

## Rationale
- Explicit context makes a non-writable installed package compatible with any
  selected writable task directory and prevents accidental package/source-relative
  data writes.
- Direct source compilation plus temporary import resolution avoids timestamp/size
  bytecode staleness and prevents same-named task helpers in different workspaces
  from contaminating each other in long-lived optimization processes.
- Keeping task meaning in user files while installing stable framework helpers
  preserves `normalized variables -> rawData -> cost` without copying framework
  implementation into every workspace.

## Impact
- Installed Python callers can select and validate workspaces, inspect effective
  config precedence, and query current task definitions/costs. The installed CLI
  remains limited to help/version/docs in this phase.
- Existing `project/` runtime paths and launchers remain current until their later
  ordered migration steps consume these APIs.
- Package step 2 is complete and archived; package step 3 (`init` and `check` CLI)
  is the next manual handoff.

## Follow-Up
- Implement `dev_doc/toDo/20260718_103602_package-03-init-and-check-cli.md` only when
  that manual toDo is explicitly triggered.
