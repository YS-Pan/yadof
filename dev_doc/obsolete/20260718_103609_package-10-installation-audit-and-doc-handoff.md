# Package Step 10: Installation Audit And Documentation Handoff

## Context

- This is the final step of the 10-step package/workspace conversion and depends on
  steps 1 through 9 being completed and archived.
- It is a closure audit, not a place to defer untested core migrations. Any missing
  behavior discovered here must be fixed and verified before completion.

## Goal

- Finish the namespace/layout cutover, prove wheel/sdist and installed behavior,
  remove obsolete source-layout assumptions, and make package + workspace + CLI the
  sole current documented workflow.

## Guidance

- Ensure all stable framework modules, CLI, tools, defaults, worker support,
  templates, and documentation live in the `yadof` package while user-editable task
  inputs and runtime outputs live only in workspaces. Remove the old `project.*`
  namespace, old root/source entry points, and pytest/repository-path crutches; add
  no legacy-layout compatibility or migration layer. Preserve the current optimize,
  evaluate-manager, job-template, recorded-data, surrogate, and tools module
  boundaries/public APIs rather than flattening them into unrelated files.
- Build and inspect wheel and sdist. Require CLI/core modules/templates/docs and
  required package data; reject active task models/inputs, workspaces, jobs, history,
  checkpoints, logs, caches, and secrets.
- In a clean environment install the wheel, make package files read-only, switch to
  a temporary directory outside the repository, and run `--help`, `version`, init,
  check, the generic local smoke/optimization path, history/view tools, and run/resume.
- Verify two workspaces remain isolated in one process and consecutive CLI calls;
  prepared jobs merge package support plus task payload; workflows create only
  rawData/metadata; dynamic costs/normalization, failure/timeout isolation, history
  recovery, surrogate checkpoints, local execution, and mocked distributed
  execution retain their current contracts.
- Run default pytest and installed-artifact integration tests without repository
  `PYTHONPATH` or imports of unpackaged source. Include at least one generic task
  test unrelated to HFSS, Ansys, a vendor, concrete model, or single adapter.
- Update `user_doc` installation/init/config/smoke/run/tool instructions and all
  affected `dev_doc` architecture, blueprints, terminology, and documentation entry
  points to the installed package/workspace design. Ensure every completed phase has
  a change record and no current document presents archived layouts as current fact.

## Verification

- Execute and record the full artifact-inspection, clean-install, repository-external,
  read-only-package, two-workspace, generic-task, local, mocked-distributed, resume,
  failure, history, surrogate, CLI, and default-pytest matrix described above.
- Inspect current source and documentation for old `project.*`, root-launcher,
  repository-path, duplicated-resource, or source-tree workspace assumptions; fix
  every remaining occurrence in scope before declaring the conversion complete.

## Documentation Rule

- Follow `dev_doc/README.md`, finish this closure phase's own current
  architecture/blueprint/user-document and terminology updates, add its change
  record, and audit that steps 1 through 9 completed their documentation work.

## Completion Rule

- A user can install yadof into a clean environment, initialize any writable
  directory, edit only workspace `config.py` and task files, then check, smoke,
  start/resume, and inspect optimization through the CLI.
- Wheel/sdist inspection, clean-install tests, repository-external integration,
  read-only-package tests, two-workspace isolation, default pytest, documentation,
  and removal of old entry points/imports all pass.
- Move this file to `dev_doc/obsolete/`; at that point the two archived master plans
  are fully completed by their successor chain.
