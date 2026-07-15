# 4+1 Development View

## Source Layout

```text
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

## Dependency Direction
- `optimize` depends on public APIs from `evaluate_manager`, `recorded_data`, `surrogate`, and `job_template` metadata.
- `evaluate_manager` depends on `job_template.api` and `recorded_data.api`.
- `recorded_data` depends on `job_template.api` for normalization and cost calculation.
- `surrogate` depends on `recorded_data.api` and `job_template.api`.
- `job_template` should not depend on other core modules.
- `job_template/workflow.py` may depend on adapter files that are in `job_template` itself. `com_lib` is only a staging/reference location and is not copied by `job_template.api`.
- Generic `tools` and `test` may depend on public APIs across modules. Simulator-
  specific tools belong under `project/tools/specific/<software>/`; `project/tools/`
  contains user tools only; administrator-only environment and cluster tools belong
  under `admin_tool/` and remain outside the runtime dependency graph.

## Development Boundaries
- API files are module gateways and should stay small.
- Internal helpers can change more freely if public API behavior and tests remain stable.
- Task-specific edits should concentrate in `project/job_template/`. Simulator adapters may be kept in `project/com_lib/` as references, but enabled adapters must be copied into `project/job_template/`.
- `project/surrogate/runtime.py` owns the training/prediction data flow; `project/surrogate/scheduler.py` owns staggered training coordination; `project/surrogate/checkpoints.py`, `metadata.py`, and `types.py` keep persistence and shared dataclasses out of the core runtime; `project/surrogate/modeling.py` owns the conditional INR internals and should not import other core modules.
- Shared settings are split between generic `project/config/key.py`, full `project/config/all.py`, and software-specific extensions under `project/config/specific/`. Task semantics must not move into generic config files.
- Core code, docs, launchers, and tools must stay portable across machines. Do not hard-code machine-specific absolute install paths, and do not introduce a requirement that users create new system environment variables before using the project. Prefer paths derived from the repository, explicit command arguments, and environment variables that external installers already provide, such as existing Conda, Ansys, or HTCondor PATH/installation variables.
- Users run against an environment already prepared by an administrator. Package
  installation, dependency repair, and HTCondor software/hardware configuration are
  administrator responsibilities, documented under `admin_tool/`.

## Test Strategy
- Use local, generic task doubles as the default verification path; `project/test/` must not start or encode assumptions about a real simulator or the active optimization task.
- Protect rawData schema and recorded-data persistence with contract tests.
- Use monkeypatched APIs for optimizer unit behavior where full local jobs would be too heavy.
- Surrogate tests may force smaller CPU INR settings so contract tests stay fast while the default config remains usable for real runs.
- Optimizer tests should cover NSGA-III reference-direction diagnostics, pooled surrogate survival, and the surrogate exploration quota without running expensive full campaigns.
- Surrogate tests should verify historical error audit, ensemble min/max interval output, and task-owned rawData importance weights with monkeypatched or small training data.
- Do not add current-task or simulator-specific tests under `project/test/`. Use ignored `temp/` for disposable task checks now; after package separation, run them in the relevant workspace. Software-specific adapter/tool tests may live beside code in the explicitly specific directories.
- HTCondor behavior should be covered with submit-file and monkeypatched-runner tests by default; real pool diagnostics are manual or explicit smoke checks.

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
