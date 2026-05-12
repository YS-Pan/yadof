# Module prompt: tests

## Intent
- Protect the v3 contracts while the implementation is still moving quickly.
- Keep the default test path local and independent of HTCondor or real simulator installations.
- Verify behavior from module public APIs whenever possible.

## Functionalities
- Closed-loop tests cover optimize -> evaluate_manager -> job_template workflow -> recorded_data -> cost.
- Default job-template tests assert the three objective names and `[0, 1]` cost bounds.
- Failure tests ensure individual prepare/run/record failures return `inf` rows and allow the generation to continue.
- Contract tests validate rawData metadata, schema versioning, flat directories, duplicate job behavior, concurrent recording, and invalid rawData diagnostics.
- Surrogate tests verify rawData-first prediction, checkpoint writing, GPSAF integration, and fallback behavior.
- Tool tests ensure `viewCost.py` uses the current recorded-data history instead of legacy JSONL files.

## I/O Format
- Tests use pytest and temporary directories.
- Basic command is `pytest -q`.
- Tests may monkeypatch public APIs to isolate module behavior.

## Non-Obvious Techniques
- Tests intentionally avoid requiring real HFSS, HTCondor, or expensive simulation software.
- Runtime temp directories are ignored through `pyproject.toml` pytest settings.
- Tests assert that problem shape comes from `job_template`, not from global config.

## Mutability Profile
- Add tests when changing shared contracts, storage layout, failure semantics, or surrogate API behavior.
- Pure task-specific changes in `job_template` may need narrower tests than core module changes.
- Generated runtime data under test temp folders should not become source documentation.
