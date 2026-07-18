# 4+1 Development View

## Source Layout

```text
README.md
pyproject.toml

src/yadof/
  __init__.py
  _version.py
  cli.py
  workspace.py
  workspace_manifest.py
  workspace_init.py
  workspace_check.py
  smoke_test.py
  config.py
  task_loader.py
  evaluate_manager/
    api.py
    job_files.py
    job_result.py
    local_runner.py
    recorded_data_client.py
    types.py
    worker_files/worker_misc.py
  recorded_data/
    api.py
    manifest_store.py
    paths.py
    query.py
    rawdata_store.py
    records.py
    utils.py
  job_template/
    api.py
    parameters_constraints_class.py
    rawdata_contract.py
    cost_misc.py
  resources.py
  _resources/templates/default/
    template.json
    workspace/

workspace/  # selected explicitly; not repository/package source
  config.py
  job_template/
    parameters_constraints.py
    workflow.py
    calc_cost.py
    *_com.py and arbitrary task assets
  jobs/
  recorded_data/
  .yadof/
    workspace.json
    surrogate/checkpoints/
    logs/
    tool_output/

dev_doc/
  README.md
  terminology.md
  architecture/
  blueprints/
  toDo/
    auto/
  change_records/
  obsolete/

user_doc/
  README.md
  package_foundation.md
  optimization_workflow.md
  workflow_typical_patterns.md
  calc_cost_typical_patterns.md
  com_lib/
    README.md
    hfss_com.md
    test_com.md
  config_and_run.md

admin_tool/
  README.md
  htcondor_doc/
  htcondor_pool/

project/
  config/
    key.py
    all.py
    specific/
  optimize/
  evaluate_manager/
  job_template/
  com_lib/
  recorded_data/
  surrogate/
  tools/
    specific/
  test/
```

`src/yadof/` now contains the installable package/resource foundation plus explicit
workspace, effective-config, isolated task-loader, safe init/check, parameter,
rawData, cost-helper, prepared-job, local-evaluation, and standalone-smoke
contracts plus workspace-local persistence. Optimization, surrogate, tools, and
distributed execution remain under `project/` until later package-conversion steps
move each module with their contracts and tests.
New packaged code uses only the `yadof` namespace; there is no `project.*`
compatibility alias.

## Dependency Direction
- The package-foundation parser/help/version/docs path depends only on `yadof`
  version/resource modules and the Python standard library. Init/check lazily import
  NumPy-backed workspace contracts only when invoked. No CLI path imports the
  still-unmigrated `project/` runtime.
- `yadof.workspace`, `yadof.config`, and `yadof.task_loader` depend only on package
  code and the standard library. `yadof.job_template` adds NumPy-backed rawData and
  cost helpers, but never imports the current `project/` tree.
- `yadof.evaluate_manager` depends on packaged config/workspace/job-template APIs
  plus `yadof.recorded_data` and standard-library subprocess/resource helpers. It
  imports no `project.*` module.
- `yadof.recorded_data` depends on explicit workspace paths and
  `yadof.job_template` for fresh normalization/cost/rawData validation. It never
  imports transitional `project.recorded_data` or selects storage from `__file__`.
- Package worker files are immutable inputs read through `importlib.resources` and
  copied into workspace jobs. Workspace task payload copies recursively around an
  explicit exclusion/reserved-name policy; no installed path becomes writable.
- Workspace `parameters_constraints.py` and `calc_cost.py` use installed
  `yadof.job_template` support. User task files are loaded from the selected
  workspace in fresh temporary namespaces; no workspace remains on `sys.path` or
  in the global module cache after a load.
- Bundled templates are immutable package resources. Their manifest explicitly maps
  safe relative sources to destinations and carries a positive template/rawData
  schema version. Init validates bytes in a sibling stage directory and never treats
  the installed resource tree as writable state.
- `optimize` depends on public APIs from `evaluate_manager`, `recorded_data`, `surrogate`, and `job_template` metadata.
- `evaluate_manager` depends on `job_template.api` and `recorded_data.api`.
- `recorded_data` depends on `job_template.api` for normalization and cost calculation.
- `surrogate` depends on `recorded_data.api` and `job_template.api`.
- `job_template` should not depend on other core modules.
- `job_template/workflow.py` may depend on adapter files that are in `job_template` itself. `com_lib` is only a staging/reference location and is not copied by `job_template.api`.
- `tools` and `test` may depend on public APIs across modules. Simulator-specific
  tools belong under `project/tools/specific/<software>/`, while all maintained
  automated tests, including software-specific tests, belong under `project/test/`.
  `project/tools/` contains user tools only; administrator-only environment and
  cluster tools belong under `admin_tool/` and remain outside the runtime dependency
  graph.

## Development Boundaries
- API files are module gateways and should stay small.
- Internal helpers can change more freely if public API behavior and tests remain stable.
- Task-specific edits should concentrate in `project/job_template/`. Simulator adapters may be kept in `project/com_lib/` as references, but enabled adapters must be copied into `project/job_template/`.
- `project/surrogate/runtime.py` owns the training/prediction data flow; `project/surrogate/scheduler.py` owns staggered training coordination; `project/surrogate/checkpoints.py`, `metadata.py`, and `types.py` keep persistence and shared dataclasses out of the core runtime; `project/surrogate/modeling.py` owns the conditional INR internals and should not import other core modules.
- Shared settings are split between generic `project/config/key.py`, full `project/config/all.py`, and software-specific extensions under `project/config/specific/`. Task semantics must not move into generic config files.
- The packaged configuration contract uses package defaults, one short workspace
  `config.py`, then temporary in-memory overrides. All effective task/runtime paths
  belong to `WorkspaceContext`; relative path values resolve from its root and only
  explicit absolute values may escape that root.
- `.yadof/workspace.json` is the only init-completion marker. It carries portable
  version/provenance fields, is published last into an existing directory, and is
  never used as permission to overwrite or repair mutable task files.
- `check` is a diagnostic boundary: task imports may validate parameter/objective
  APIs, workflow is syntax-parsed only, backend programs are located but not run,
  and no installation/repair behavior belongs in this command.
- `smoke-test` is an execution boundary, not an extension of check. It executes one
  midpoint local workflow without timeout. Exact unchanged generic template bytes
  are the only implicit-safe case; other tasks require `--real-task`.
- Prepared jobs receive `worker_misc.py` and `yadof_worker_config.json` from package
  code. These names are reserved at workspace task root. The JSON contains only
  local mode/timeout/worker-count values with sources plus version/workspace
  provenance, never a copy of package config source.
- Recorded-data public calls receive an effective `WorkspaceContext` (or an explicit
  root using default paths). Configured custom paths are preserved by passing
  `load_config(...).workspace`; module globals never carry a previous workspace's
  storage or task state.
- Core code, docs, launchers, and tools must stay portable across machines. Do not hard-code machine-specific absolute install paths, and do not introduce a requirement that users create new system environment variables before using the project. Prefer paths derived from the repository, explicit command arguments, and environment variables that external installers already provide, such as existing Conda, Ansys, or HTCondor PATH/installation variables.
- Users run against an environment already prepared by an administrator. Package
  installation, dependency repair, and HTCondor software/hardware configuration are
  administrator responsibilities, documented under `admin_tool/`.
- `pyproject.toml` owns distribution metadata, dependency layers, the `yadof`
  console entry point, and build-time document mapping. Runtime version consumers
  use `yadof.__version__`, whose single source is `src/yadof/_version.py`.
- Root `dev_doc/` and `user_doc/` remain the only editable documentation sources.
  Do not hand-copy them below `src/`; the build backend force-includes them only in
  built wheel contents.

## Test Strategy
- `project/test/` is the only source location for maintained automated tests. Do not place pytest modules beside implementation code, including software-specific tools or adapters.
- Use local, generic task doubles as the default verification path. Reusable tests for a particular simulator, adapter, or software-specific tool may also live under `project/test/`, but they must use mocks or synthetic data and must not require the external software during the default test run.
- Protect rawData schema and recorded-data persistence with contract tests.
- Use monkeypatched APIs for optimizer unit behavior where full local jobs would be too heavy.
- Surrogate tests may force smaller CPU INR settings so contract tests stay fast while the default config remains usable for real runs.
- Optimizer tests should cover NSGA-III reference-direction diagnostics, pooled surrogate survival, and the surrogate exploration quota without running expensive full campaigns.
- Surrogate tests should verify historical error audit, ensemble min/max interval output, and task-owned rawData importance weights with monkeypatched or small training data.
- Do not add current-task tests under `project/test/`. A test is current-task-specific when it hard-codes a concrete model/input filename or design, a concrete objective such as `S11`, the active task's exact variable count/names/ranges/units, expected physical results, or assertions against active `project/job_template/` task files. Neutral generated resource names and minimal synthetic problem shapes remain valid reusable fixtures.
- Put a task-specific test and all of its supporting files under ignored root `temp/`, where they must remain safe to delete at any time; after package separation, keep them in the relevant task workspace.
- HTCondor behavior should be covered with submit-file and monkeypatched-runner tests by default; real pool diagnostics are manual or explicit smoke checks.
- `project/test/test_package_foundation.py` protects distribution metadata, the
  foundation CLI, version/resource access, wheel/sdist contents, repository-external
  clean installation, external init/check, and unchanged read-only package files.
  Artifact checks run when the declared development build tools are installed.
- `project/test/test_workspace_config_task_loaders.py` protects config precedence,
  validation, path resolution, assigned parameter snapshots, same-process edits,
  and complete two-workspace import/cache isolation.
- `project/test/test_workspace_init_check_cli.py` protects exact generic-template
  contents, marker portability, idempotence/conflicts, user-content preservation,
  non-interactive execution, validation/publish rollback, static rawData/backend
  diagnostics, and the no-workflow-execution boundary.
- `project/test/test_packaged_local_evaluation.py` protects package/task composition,
  multiple adapters/assets, reserved collisions, assigned values, definition-only
  static hashing, provenance/effective config, success/failure/timeout isolation,
  no-cost boundaries, workspace recording/path overrides, record-failure isolation,
  and standalone smoke safety/exactly-one behavior.
- `project/test/test_packaged_recorded_data.py` protects two-workspace isolation,
  current-range/current-cost reinterpretation, invalid-data diagnostics, failed
  record visibility, JSONL recovery/overwrite, and concurrent manifest/archive
  writes.
- Package artifact integration additionally runs successful, failed, and timed-out
  local jobs from an installed wheel outside the repository while site-packages is
  non-writable, then compares installed-package and repository-source hashes and
  confirms every record/lock/archive/temp path remains workspace-owned.

## Documentation Strategy
- `dev_doc/README.md` is the documentation entry point and writing guide.
- `user_doc/README.md` is the user-facing task documentation entry point. A
  `dev_doc` pass must read it and follow its guide; a `user_doc` pass must not
  read `dev_doc` unless the user separately asks for framework development context.
- `admin_tool/README.md` is the entry point for administrator-only environment and
  HTCondor-pool resources. `admin_tool/htcondor_pool/htcondor_pool.ps1` configures
  one parameterized manager or worker node in one managed block; its optional
  diagnostic action remains outside the runtime graph. These are not user
  task-setup instructions.
- `dev_doc/architecture/` captures current design views, core invariants, runtime flows, and system-level contracts; it must be read in full for context.
- `dev_doc/blueprints/00_project.md` is the generative project-level contract.
- `dev_doc/blueprints/` captures module intent, I/O, non-obvious techniques,
  mutability boundaries, and useful historical reference ancestry; list all blueprint
  files first, then read relevant files in full. File-level blueprints under
  `blueprints/20_files/` mirror source paths, for example
  `blueprints/20_files/project/surrogate/runtime.py.md`.
- `dev_doc/terminology.md` captures project-specific concepts and must be read in full for context.
- `dev_doc/toDo/` captures pending future work and must be read recursively in full
  during the first `dev_doc` pass. Files directly in that folder use the default
  manual trigger and execute only when the prompt explicitly requests the
  instructions from a particular file. `dev_doc/toDo/auto/` contains automatic
  trigger items for incidental, low-priority improvements; they may be applied when
  normal in-scope work reveals a matching occurrence, but must not cause a dedicated
  repository search or scope expansion.
- Each automatic toDo is checked when read. The default obsolete policy parses the
  leading `YYYYMMDD_HHMMSS` filename timestamp as local wall-clock creation time
  and uses a seven-day limit. A document may configure a different time limit
  and/or an objective user-defined condition; the latter is absent by default and
  must not be inferred from project changes. Time expiry is strict: a document is
  archived only after its exact deadline, not at it. A `manual` rule disables
  automatic obsoletion. Fully completed manual and automatic toDos still move to
  `obsolete/`.
- `dev_doc/change_records/` captures what changed and why; do not read it by default.
- `dev_doc/obsolete/` is archival, including completed toDo handoffs, and should not be read by default.
- User-facing workflow, adapter, cost, config, smoke-test, and launch instructions
  belong under `user_doc/`; avoid duplicating those details in `dev_doc`.
- After each code change, update relevant architecture and blueprint files, add a change record, and update terminology when a concept was misunderstood or a non-obvious term was introduced.
- Package builds include both documentation trees as read-only resources without
  making the generated wheel paths authoritative source locations. Installed CLI
  document lookup prints content and does not require a GUI or writable package.
