# 4+1 Development View

## Source Layout

```text
dev_doc/
  README.md
  spec 20260502.md
  terminology.md
  reference_map.md
  architecture/
  prompt/
  toDo/
  change_records/
  obsolete/

project/
  optimize/
  evaluate_manager/
  job_template/
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
- `tools` and `test` may depend on public APIs across modules.

## Development Boundaries
- API files are module gateways and should stay small.
- Internal helpers can change more freely if public API behavior and tests remain stable.
- Task-specific edits should concentrate in `project/job_template/`.
- `project/surrogate/runtime.py` owns the cross-module API boundary; `project/surrogate/modeling.py` owns the conditional INR internals and should not import other core modules.
- Shared settings should stay in `project/config.py`, but task semantics should not move there.

## Test Strategy
- Use local mode as the default verification path.
- Protect rawData schema and recorded-data persistence with contract tests.
- Use monkeypatched APIs for optimizer unit behavior where full local jobs would be too heavy.
- Surrogate tests may force smaller CPU INR settings so contract tests stay fast while the default config remains usable for real runs.
- Avoid adding tests that require real HFSS or HTCondor for the default suite.

## Documentation Strategy
- `dev_doc/README.md` is the documentation entry point and writing guide.
- `dev_doc/spec 20260502.md` is the highest-level product and architecture contract.
- `dev_doc/architecture/` captures current design views and must be read in full for context.
- `dev_doc/prompt/` captures generative module intent and non-obvious techniques; list all prompt files first, then read relevant files in full.
- `dev_doc/reference_map.md` captures old-project ancestry and must be read in full for context.
- `dev_doc/terminology.md` captures project-specific concepts and must be read in full for context.
- `dev_doc/toDo/` captures pending future work and must be read in full during the first `dev_doc` pass.
- `dev_doc/change_records/` captures what changed and why; do not read it by default.
- `dev_doc/obsolete/` is archival, including completed toDo handoffs, and should not be read by default.
- After each code change, update relevant architecture and prompt files, add a change record, and update terminology when a concept was misunderstood or a non-obvious term was introduced.
