# Module blueprint: tests

## Intent
- Protect the v3 contracts while the implementation is still moving quickly.
- Keep the default test path local and independent of HTCondor or accidental real HFSS launches; real HFSS smoke tests must be explicitly enabled.
- Verify behavior from module public APIs whenever possible.

## Historical Lineage
- The test suite is driven by current v3 contracts plus old prompt invariants: local mode must work by default, rawData stays flat, cost is dynamic, failures are isolated, and surrogate remains rawData-first.
- Old project tests are historical context only; current tests should verify public APIs and storage contracts in this workspace.

## Functionalities
- Closed-loop tests cover optimize -> evaluate_manager -> job_template workflow -> recorded_data -> cost.
- Default job-template tests assert the current antenna task parameter names, objective names, and `[0, 1]` cost bounds using small HFSS-like rawData fixtures. These assertions should follow the active `job_template` task rather than treating an old simulation filename as a framework constant.
- Failure tests ensure individual prepare/run/record failures return `inf` rows and allow the generation to continue.
- HTCondor tests cover submit-file generation, submit failure capture, and distributed-mode finalization through monkeypatched command execution.
- Contract tests validate rawData metadata, metadata compaction, workflow-owned timing, schema versioning, flat directories, duplicate job behavior, concurrent recording, and invalid rawData diagnostics.
- Surrogate tests verify rawData-first prediction, conditional-INR checkpoint/artifact writing, GPSAF integration, and fallback behavior.
- Optimizer tests verify NSGA-III reference-direction diagnostics, absence of NSGA-II optimizer imports, pooled surrogate survival, and the surrogate exploration quota.
- Surrogate tests verify historical error audit, non-zero imperfect-model error reporting, ensemble min/max interval output, and task-owned rawData importance weights.
- Tool tests ensure `viewCost.py` uses the current recorded-data history instead of legacy JSONL files.

## I/O Format
- Tests use pytest and temporary directories.
- Basic command is `pytest -q`.
- Tests may monkeypatch public APIs to isolate module behavior.

## Non-Obvious Techniques
- Tests intentionally avoid requiring real HFSS, HTCondor, or expensive simulation software unless a real-HFSS smoke-test flag is set.
- Tests for distributed mode should mock `condor_submit`/runner behavior unless they are explicit environment smoke tests requested by the user.
- Runtime temp directories are ignored through `pyproject.toml` pytest settings.
- Tests assert that problem shape comes from `job_template`, not from global config.
- Local pipeline tests should assert that `individual_metadata.json` exists in job folders and that recorded individual rows promote `started_at`, `ended_at`, `optimization_index`, and `generation_index` without persisting `created_at`.

## Mutability Profile
- Add tests when changing shared contracts, storage layout, failure semantics, or surrogate API behavior.
- Pure task-specific changes in `job_template` may need narrower tests than core module changes.
- Generated runtime data under test temp folders should not become source documentation.
