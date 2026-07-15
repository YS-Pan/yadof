# Module blueprint: tests

## Intent
- Protect the current contracts while the implementation is still moving quickly.
- Keep the default test path local, software-agnostic, and independent of HTCondor or real simulator launches.
- Verify behavior from module public APIs whenever possible.

## Historical Lineage
- The test suite is driven by current contracts plus durable prompt invariants: local mode must work by default, rawData stays flat, cost is dynamic, failures are isolated, and surrogate remains rawData-first.
- Old project tests are historical context only; current tests should verify public APIs and storage contracts in this workspace.

## Functionalities
- Closed-loop tests cover optimize -> evaluate_manager -> job_template workflow -> recorded_data -> cost.
- Framework tests use generic task doubles and neutral rawData fixtures. They must not assert the active task's parameter names/count, objective names/count, simulator expressions, model filename, or expected task results.
- Failure tests ensure individual prepare/run/record failures return `inf` rows and allow the generation to continue.
- HTCondor tests cover submit-file generation, submit failure capture, and distributed-mode finalization through monkeypatched command execution.
- Contract tests validate rawData metadata, metadata compaction, workflow-owned timing, schema versioning, flat directories, duplicate job behavior, concurrent recording, and invalid rawData diagnostics.
- Parameter handoff tests validate assigned continuous/discrete/mixed values,
  same-process range refresh, job-local snapshots, definition-only static hashes,
  historical re-normalization, and local/distributed absence of JSON variable inputs.
- Surrogate tests verify rawData-first prediction, conditional-INR checkpoint/artifact writing, GPSAF integration, and fallback behavior.
- Optimizer tests verify NSGA-III reference-direction diagnostics, absence of NSGA-II optimizer imports, pooled surrogate survival, and the surrogate exploration quota.
- Surrogate tests verify historical error audit, non-zero imperfect-model error reporting, ensemble min/max interval output, and task-owned rawData importance weights.
- Tool tests ensure `viewCost.py` uses the current recorded-data history instead of legacy JSONL files.

## I/O Format
- Tests use pytest and temporary directories.
- Basic command is `pytest -q`.
- Tests may monkeypatch public APIs to isolate module behavior.
- `project/test/README.md` is the direct contributor-facing scope rule for the generic test directory.

## Non-Obvious Techniques
- Tests under `project/test/` must not contain current-task or simulator-specific scenarios, even behind an opt-in flag.
- If a current task temporarily needs a regression or smoke test before package separation, place it under the ignored root `temp/` directory and assume it may be deleted at any time. After package/workspace separation, keep and run such tests inside that task's workspace.
- Software-specific helper/adapter tests may live beside the software-specific code under `project/tools/specific/<software>/` or `project/com_lib/`; they are not part of the generic default `project/test/` suite.
- Tests for distributed mode should mock `condor_submit`/runner behavior unless they are explicit environment smoke tests requested by the user.
- Runtime temp directories are ignored through `pyproject.toml` pytest settings.
- Tests assert that problem shape comes from `job_template`, not from global config.
- Local pipeline tests should assert that `individual_metadata.json` exists in job folders and that recorded individual rows promote `started_at`, `ended_at`, `optimization_index`, and `generation_index` without persisting `created_at`.

## Mutability Profile
- Add tests when changing shared contracts, storage layout, failure semantics, or surrogate API behavior.
- Do not add task-specific tests under `project/test/`. Use `temp/` now or the task workspace after package separation.
- Generated runtime data under test temp folders should not become source documentation.
