# Package Step 6: Optimize And Surrogate Workspaces

## Context

- This is step 6 of 10 and depends on step 5 being completed and archived.
- Local jobs and durable history now use explicit workspaces; the optimizer and
  surrogate must consume those APIs without reverting to implicit source paths or
  global task state.

## Goal

- Migrate `optimize` and `surrogate` into the installed package and explicit
  workspace context.
- Preserve search, recovery, rawData-first prediction, checkpoints, and failure
  isolation while making multiple workspaces independent.

## Guidance

- Convert framework imports to `yadof.*` or package-relative imports and pass the
  active workspace/context through public optimize, recorded-data, job-template,
  evaluate, and surrogate boundaries.
- Preserve current single-/multi-objective generation behavior, historical warm
  start, dynamic cost/normalization, run/generation metadata, GPSAF pressure,
  exploration quota, and per-individual `inf` failure handling.
- Store every surrogate checkpoint/member artifact and optimization metadata below
  the active workspace. Training and prediction must use only that workspace's
  records, task cost path, config, and checkpoints.
- Retain the rawData-first surrogate contract, audited predictions, ensemble cost
  intervals, task-owned importance weights, staggered training/freshness rules, and
  resume semantics. Do not make cost a persisted truth during relocation.
- Public Python APIs must be able to start/resume generations with an explicit
  workspace even before the final `yadof run` command is added.

## Verification

- Test baseline and surrogate-assisted generations, history recovery, checkpoint
  paths, changed task definitions, failures, and staggered training through the
  installed package.
- Alternate two workspaces in one process and in consecutive calls; verify no
  optimizer state, config, task modules, history, or checkpoint cross-contamination.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- Optimize and surrogate behavior is workspace-scoped and the existing algorithmic
  contracts still pass. Archive this file, then execute step 7.
