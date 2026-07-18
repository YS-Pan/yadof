# 2026-07-18 11:15 - Establish Package Build And Resource Foundation

## Context

- Yadof had a modular runtime under `project/` and pytest configuration in
  `pyproject.toml`, but no installable distribution metadata, `yadof` import package,
  console entry point, runtime version source, or installed documentation access.
- Package step 1 requires a testable installed boundary before runtime modules and
  user workspaces are migrated in later ordered steps.

## Change

- Added a Hatchling PEP 517 configuration for the `yadof` distribution with Python
  support metadata, base NumPy/pymoo dependencies, optional surrogate/plot/HFSS/dev
  groups, source layout selection, project URLs, and a `yadof` console script.
- Added `src/yadof/` with version `0.1.0`, public `__version__`, `python -m yadof`,
  standard-library help/version/document CLI behavior, and read-only resource APIs.
- Kept root `dev_doc/` and `user_doc/` authoritative while mapping them into wheel
  package data at build time; sdists preserve the root layout for reproducible
  builds. Added a software-neutral default template resource foundation.
- Added package artifact tests that build wheel/sdist, audit contents, install the
  wheel without dependencies in a clean repository-external virtual environment,
  make package files non-writable, and run the generated console command.
- Added package-foundation user/current architecture/blueprint/terminology updates
  while documenting that optimization runtime modules still remain under
  `project/` for later migration.

## Rationale

- Hatchling's build-time file mapping includes the authoritative documentation in
  wheels without maintaining hand-synchronized source copies under `src/`.
- A small standard-library CLI keeps base installation and document/version checks
  independent of external simulators, HTCondor, plotting, and surrogate libraries.
- Explicitly retaining the current runtime boundary prevents the foundation from
  becoming a `project.*` compatibility layer or falsely advertising later stages as
  complete.

## Impact

- Clean environments can install a built wheel and run `yadof --help`,
  `yadof --version`, `yadof version`, and `yadof docs user|dev` outside the source
  repository with read-only package files.
- Existing runtime imports, launchers, data paths, optimization behavior, and the
  `normalized variables -> rawData -> cost` contract are unchanged in this stage.
- Developers need the `dev` extra to execute artifact-building integration tests;
  source metadata/CLI/resource tests remain available without those build tools.

## Follow-Up

- Package step 2 introduces explicit workspace, config, and task loaders before any
  current runtime module is moved into the installed namespace.
