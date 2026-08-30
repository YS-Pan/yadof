# Package Step 2: Workspace, Config, And Task Loaders

> Completed and archived on 2026-07-18. Explicit workspace paths, effective config
> precedence/validation, source-fresh isolated task loading, installed job-template
> framework support, tests, current documentation, and this phase's change record
> are in place. Package step 3 is now the next manual handoff.

## Context

- This is step 2 of 10 and depends on step 1 being completed and archived.
- The installed package is read-only framework code; a workspace is the explicit,
  writable root for one task and its runtime state. The current directory is only
  the default workspace selection.

## Goal

- Introduce an explicit workspace context, package-default plus workspace-override
  configuration, and isolated loading of user-owned task modules.
- Preserve the dynamic `normalized variables -> rawData -> cost` contract while
  removing implicit binding to package/source-relative task and data paths.

## Guidance

- Define a public workspace context containing root, `config.py`, `job_template/`,
  jobs, recorded data, surrogate checkpoints, logs, and tool-output paths. Every
  path must derive from the selected workspace or an explicit absolute override;
  no user-data path may derive from package `__file__`.
- Implement one config loader that merges package defaults with a short workspace
  `config.py`, validates unknown names/types/modes/task paths before batch work,
  supports documented temporary CLI overrides without rewriting the file, and can
  show the final values and precedence.
- Move the stable job-template framework API, parameter class, rawData contract,
  cost helpers, and loaders into the installed package. A workspace `job_template/`
  owns only `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, active
  `*_com.py` adapters, simulator/custom inputs, lookup tables, and other task assets.
- Load submit-side task modules from the selected workspace in isolated namespaces.
  Support their reasonable local imports without permanently adding the workspace
  to `sys.path`; specify reload/cache invalidation so allowed edits between
  generations are visible and two workspaces cannot contaminate each other.
- Keep task variables, objective/rawData meaning, simulator filenames, and adapter
  selection out of global config. Continue deriving cost and historical normalized
  variables from current task files rather than persisting them as source truth.
- Do not create a legacy layout migrator, `project.*` alias, dual data format, or
  compatibility wrapper.

## Verification

- Test config validation, precedence, relative/absolute paths, and non-mutating CLI
  overrides.
- In one Python process, alternate between two workspaces with different configs and
  task modules; verify fresh edits and complete path/module/cache isolation.
- Make installed package resources read-only and verify all writable paths still
  resolve into the workspace.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- Workspace, config, and task-loading public contracts are stable, tested, and
  documented. Move this file to `dev_doc/obsolete/`, then execute step 3.
