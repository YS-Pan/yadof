# Package Step 1: Build And Resource Foundation

## Context

- This is step 1 of 10 in the package/workspace conversion sequence split from
  `dev_doc/obsolete/20260703 package.md`.
- This step establishes an installable package boundary before runtime modules are
  moved. It must not add compatibility shims for `project.*` or the old root
  launchers.
- Later steps may temporarily leave unmigrated source under `project/`, but new
  packaged code must use the final `yadof` namespace from the start.

## Goal

- Establish the `yadof` distribution, runtime version source, console entry point,
  dependency groups, and read-only package resources.
- Make the smallest installed CLI usable outside the repository without claiming
  that the runtime migration is already complete.

## Guidance

- Add and validate `pyproject.toml` build-system and project metadata: distribution,
  command, and public import names are all `yadof`; declare the supported Python
  range, core dependencies, optional surrogate/plot/development/simulator groups,
  package data, and the `yadof` console script.
- Create the `src/yadof/` package foundation and one authoritative version value
  shared by package metadata, `yadof version`, future workspace markers, and job
  metadata.
- Add the minimal CLI framework with consistent help, error, exit-code, and
  stdout/stderr conventions. At this stage only repository-independent commands
  such as `--help`, `version`, and packaged-document lookup need to work.
- Package the authoritative `dev_doc/`, `user_doc/`, software-neutral initialization
  templates, and other required framework resources into wheel and sdist without
  maintaining hand-copied duplicate document trees. Access them through
  `importlib.resources` or an equivalent API that works for non-writable resources.
- Do not include current task models, task-specific inputs, jobs, recorded data,
  checkpoints, logs, caches, or secrets in artifacts.
- Keep simulator programs and HTCondor executables outside pip dependencies; they
  remain administrator-provided external environment components.

## Verification

- Build wheel and sdist and inspect their contents.
- Install the wheel into a clean environment and, from outside the repository, run
  `yadof --help`, `yadof version`, and the non-GUI documentation lookup.
- Verify these commands do not rely on repository `PYTHONPATH`, the current source
  directory, or writable package resources.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- The package foundation and resource/version contracts are tested and documented.
- Move this file to `dev_doc/obsolete/` only after completion, then execute step 2.
