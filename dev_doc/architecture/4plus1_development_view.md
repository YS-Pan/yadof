# 4+1 Development View

## Source Layout

```text
dev_doc/
  README.md
  spec 20260502.md
  terminology.md
  reference_map.md
  architecture/
  blueprints/
  toDo/
  change_records/
  obsolete/

project/
  optimize/
  evaluate_manager/
  job_template/
  com_lib/
  recorded_data/
  surrogate/
  tools/
  test/
  config.py
```

## Dependency Direction
- `optimize` depends on public APIs from `evaluate_manager`, `recorded_data`, `surrogate`, and `job_template` metadata.
- `evaluate_manager` depends on `job_template.api` and `recorded_data.api`.
- `recorded_data` depends on `job_template.api` for normalization and cost calculation.
- `surrogate` depends on `recorded_data.api` and `job_template.api`.
- `job_template` should not depend on other core modules.
- `job_template/workflow.py` may depend on adapter files that are in `job_template` itself. `com_lib` is only a staging/reference location and is not copied by `job_template.api`.
- `tools` and `test` may depend on public APIs across modules.

## Development Boundaries
- API files are module gateways and should stay small.
- Internal helpers can change more freely if public API behavior and tests remain stable.
- Task-specific edits should concentrate in `project/job_template/`. Simulator adapters may be kept in `project/com_lib/` as references, but enabled adapters must be copied into `project/job_template/`.
- `project/surrogate/runtime.py` owns the cross-module API boundary; `project/surrogate/modeling.py` owns the conditional INR internals and should not import other core modules.
- Shared settings should stay in `project/config.py`, but task semantics should not move there.

## Test Strategy
- Use local mode as the default verification path, but do not start real HFSS unless an explicit HFSS smoke-test flag or manual command requests it.
- Protect rawData schema and recorded-data persistence with contract tests.
- Use monkeypatched APIs for optimizer unit behavior where full local jobs would be too heavy.
- Surrogate tests may force smaller CPU INR settings so contract tests stay fast while the default config remains usable for real runs.
- Optimizer tests should cover NSGA-III reference-direction diagnostics, pooled surrogate survival, and the surrogate exploration quota without running expensive full campaigns.
- Surrogate tests should verify historical error audit, ensemble min/max interval output, and task-owned rawData importance weights with monkeypatched or small training data.
- Avoid adding tests that require real HFSS or HTCondor for the default suite.
- HTCondor behavior should be covered with submit-file and monkeypatched-runner tests by default; real pool diagnostics are manual or explicit smoke checks.

## Documentation Strategy
- `dev_doc/README.md` is the documentation entry point and writing guide.
- `dev_doc/spec 20260502.md` is the highest-level product and architecture contract.
- `dev_doc/architecture/` captures current design views and must be read in full for context.
- `dev_doc/blueprints/` captures generative module intent and non-obvious techniques; list all blueprint files first, then read relevant files in full.
- `dev_doc/reference_map.md` captures old-project ancestry and must be read in full for context.
- `dev_doc/terminology.md` captures project-specific concepts and must be read in full for context.
- `dev_doc/toDo/` captures pending future work and must be read in full during the first `dev_doc` pass.
- `dev_doc/change_records/` captures what changed and why; do not read it by default.
- `dev_doc/obsolete/` is archival, including completed toDo handoffs, and should not be read by default.
- After each code change, update relevant architecture and blueprint files, add a change record, and update terminology when a concept was misunderstood or a non-obvious term was introduced.
