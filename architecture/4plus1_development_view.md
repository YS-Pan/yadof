# 4+1 Development View

## Source Layout

```text
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
- `prompt/` captures module intent and non-obvious techniques.
- `reference_map.md` captures old-project ancestry.
- `architecture/` captures current design views.
- These docs should be updated when module contracts shift.
