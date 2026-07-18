# Module blueprint: tests

## Intent
- Protect the current contracts while the implementation is still moving quickly.
- Keep the default test path local and independent of HTCondor or real simulator launches.
- Centralize all maintained automated tests under `project/test/`, including reusable software-specific tests.
- Verify behavior from module public APIs whenever possible.

## Historical Lineage
- The test suite is driven by current contracts plus durable prompt invariants: local mode must work by default, rawData stays flat, cost is dynamic, failures are isolated, and surrogate remains rawData-first.
- Old project tests are historical context only; current tests should verify public APIs and storage contracts in this workspace.

## Functionalities
- Package-foundation tests validate standardized metadata, the single version
  source, CLI stdout/stderr behavior, source and installed resource lookup, and
  software-neutral template resources.
- Workspace/config/task-loader tests validate absolute path resolution, no
  construction writes, precedence/source reporting, unknown/type/mode/task-path
  errors, explicit relative/absolute overrides, and non-mutating temporary values.
- One-process tests alternate two workspaces with same-named local modules, edit
  config/task helpers without sleeping or changing source size, and prove fresh
  results plus unchanged `sys.path`, restored `sys.modules`, and no task bytecode
  cache.
- Artifact integration builds wheel and sdist, inspects their allow/deny content,
  installs the wheel without dependencies into a clean external virtual environment,
  makes package files non-writable, and runs help/version/document commands.
- Closed-loop tests cover optimize -> evaluate_manager -> job_template workflow -> recorded_data -> cost.
- Framework tests use generic task doubles and neutral rawData fixtures. They must not assert the active task's parameter names/count, objective names/count, simulator expressions, model filename, or expected task results.
- Software-specific tests may verify reusable adapters, file formats, and tools. They use mocks, synthetic data, and generated temporary resource names instead of the active task or a real simulator launch.
- Failure tests ensure individual prepare/run/record failures return `inf` rows and allow the generation to continue.
- HTCondor tests cover submit-file generation, adaptive resource/time selection,
  no-timeout smoke submission, ClassAd resource/time metadata capture, duration-hold
  classification/removal, absence of native resource-retry directives, yadof
  memory/disk hold classification and bounded fresh resubmission, submit failure
  capture, and distributed-mode finalization through monkeypatched command execution.
- Contract tests validate rawData metadata, metadata compaction, workflow-owned timing, schema versioning, flat directories, duplicate job behavior, concurrent recording, and invalid rawData diagnostics.
- Parameter handoff tests validate assigned continuous/discrete/mixed values,
  same-process range refresh, job-local snapshots, definition-only static hashes,
  historical re-normalization, and local/distributed absence of JSON variable inputs.
- Surrogate tests verify rawData-first prediction, conditional-INR checkpoint/artifact writing, GPSAF integration, and fallback behavior.
- Optimizer tests verify NSGA-III reference-direction diagnostics, absence of NSGA-II optimizer imports, pooled surrogate survival, and the surrogate exploration quota.
- Surrogate tests verify historical error audit, non-zero imperfect-model error reporting, ensemble min/max interval output, and task-owned rawData importance weights.
- Tool tests ensure `viewCost.py` uses the current recorded-data history instead of legacy JSONL files.

## I/O Format
- Package artifact tests require the declared `dev` build dependencies. When those
  tools are absent, only the artifact integration test is skipped with an actionable
  reason; metadata/CLI/resource source tests still run.
- Tests use pytest and temporary directories.
- Basic command is `pytest -q`.
- Tests may monkeypatch public APIs to isolate module behavior.
- `project/test/README.md` is the direct contributor-facing scope and placement rule.

## Non-Obvious Techniques
- Clean-install verification removes inherited `PYTHONPATH`/`PYTHONHOME`, runs from a
  system temporary directory outside the repository, invokes the generated console
  wrapper, and hashes installed package files before/after read-only commands.
- The read-only clean-install check also resolves workspace writable paths, loads
  effective config, and imports a task module with a local helper. It asserts those
  actions change neither the installed-package hashes nor global `sys.path`.
- No maintained pytest module lives beside production code. `project/test/` is the only test source directory, including for software-specific helpers and adapters.
- Tests under `project/test/` must not contain current-task scenarios, even behind an opt-in flag. Task specificity includes concrete task filenames/designs, concrete objectives such as `S11`, the active task's exact variable count/names/ranges/units, expected physical results, and assertions against active `project/job_template/` task files.
- Neutral generated filenames and minimal synthetic variable/objective shapes are allowed when they exercise a reusable contract rather than reproduce the active task.
- If a current task temporarily needs a regression or smoke test before package separation, place the test and every supporting file under the ignored root `temp/` directory and assume all of them may be deleted at any time. After package/workspace separation, keep and run such tests inside that task's workspace.
- Tests for distributed mode should mock `condor_submit`/runner behavior unless they are explicit environment smoke tests requested by the user.
- Runtime temp directories are ignored through `pyproject.toml` pytest settings.
- Tests assert that problem shape comes from `job_template`, not from global config.
- Local pipeline tests should assert that `individual_metadata.json` exists in job folders and that recorded individual rows promote `started_at`, `ended_at`, `optimization_index`, and `generation_index` without persisting `created_at`.

## Mutability Profile
- `project/test/test_workspace_config_task_loaders.py` is the focused contract suite
  for package step 2. Keep future workspace APIs explicit and extend this suite when
  adding a new writable path, config setting type, or task loading behavior.
- Add tests when changing shared contracts, storage layout, failure semantics, or surrogate API behavior.
- Do not add task-specific tests under `project/test/`. Use `temp/` now or the task workspace after package separation.
- Add software-specific tests under `project/test/`, never next to the implementation they cover.
- Generated runtime data under test temp folders should not become source documentation.
