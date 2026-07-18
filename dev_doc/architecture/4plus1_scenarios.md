# 4+1 Scenarios

## Scenario 1: First Local Generation
1. User edits `project/job_template/parameters_constraints.py`, `workflow.py`, `calc_cost.py`, and any needed adapter file placed in `project/job_template`.
2. User calls `project.optimize.api.run_one_generation()`.
3. `optimize` has no history, so it samples normalized candidates.
4. `evaluate_manager` fresh-loads the current parameter definitions, materializes an
   assigned job-local parameter snapshot with run/generation context in submit-side
   metadata, and runs `workflow.py`.
5. `workflow.py` reads `parameter.value` from that snapshot, writes each individual's
   start/end metadata, and uses any active copied adapter files to write task-specific
   flat rawData.
6. `recorded_data` stores raw variables, rawData, compact metadata, optimization index, and generation index.
7. The current task costs are calculated dynamically and returned to `optimize`.

## Scenario 2: Resume From History
1. `optimize` asks `recorded_data` for historical optimization results.
2. `recorded_data` normalizes stored raw variables with current parameter ranges.
3. `recorded_data` recalculates costs with current `calc_cost.py`.
4. `optimize` seeds the optimizer state from compatible historical records.

## Scenario 3: Use Surrogate Assistance
1. User increases `OPTIMIZE_SURROGATE_ALPHA` or `OPTIMIZE_SURROGATE_BETA`.
2. `optimize` trains `surrogate` from completed records.
3. `surrogate` flattens recorded rawData, applies task-owned importance weights, audits historical prediction error, trains or refreshes the conditional INR ensemble, and writes a generation checkpoint plus member artifacts.
4. `surrogate` predicts rawData for alpha/beta candidate pools.
5. `surrogate` calculates predicted costs and ensemble member min/max intervals through `job_template.api`.
6. `optimize` selects a real population with pooled NSGA-III survival while reserving a small exploration quota, then sends it to `evaluate_manager`.

## Scenario 4: Evaluation Failure
1. One job preparation, workflow run, timeout, or recording step fails.
2. `evaluate_manager` combines workflow-owned metadata, when present, with runner diagnostics and records best effort.
3. The failed individual receives `inf` costs.
4. Other individuals in the generation continue.
5. Failure records remain visible in `recorded_data`, but default history excludes non-completed records.

## Scenario 5: Modify Task Mid-Campaign
1. User changes parameter ranges, workflow, simulator file, or `calc_cost.py`.
2. The next job fresh-loads the edited ranges and receives assigned raw values
   calculated from those ranges; no optimization-process restart is required.
3. New jobs get a different static hash when parameter definitions or other static
   inputs change, while different assigned individual values share the same hash.
4. Old rawData remains stored.
5. Historical normalized variables and costs are recalculated under the current task definition.
6. If the change makes old rawData semantically invalid, the user manually removes or ignores old records.

## Scenario 6: Distributed Evaluation
1. `evaluate_manager` selects distributed mode through `EVALUATION_MODE = "distributed"` or an explicit API argument.
2. It prepares the same job folder contract.
3. `condor_runner.py` writes `job.sub`, then calls `condor_submit` without changing the HTCondor installation.
4. HTCondor workers run the transferred `workflow.py` executable directly and transfer generated outputs back to the job folder.
5. If HTCondor holds an attempt for standard memory or disk exhaustion, yadof removes the old cluster and freshly submits the same prepared individual with only that resource doubled; no `retry_request_*` directives are present in `job.sub`.
6. Finalization reuses the shared job metadata and `recorded_data` write path, including yadof retry history when applicable.
7. Optimizer receives the same cost tuple shape as in local mode.

## Scenario 7: Code Change With Documentation Update
1. AI or user changes source behavior, module contracts, persistence behavior, or important implementation technique.
2. The relevant `dev_doc/architecture/` files are updated when the change affects system views, dependencies, data flow, or workflow.
3. The relevant `dev_doc/blueprints/` files are updated when the change affects module intent, I/O, non-obvious techniques, or mutability boundaries.
4. A new file is appended under `dev_doc/change_records/` with a date-time prefix and a short description.
5. `dev_doc/terminology.md` is updated if the change corrects a concept or introduces a non-obvious name.

## Scenario 8: Launch With Automatic Time Calibration
1. `start_optimization_from_config.py` reads `OPTIMIZE_SMOKE_TEST_ENABLED` from the key/full config surface.
2. When enabled, it evaluates one midpoint individual in the configured backend with no timeout and stops before optimization if the smoke result has no finite cost.
3. Generation zero submits each normal Condor job with `allowed_execute_duration = smoke duration * HTCONDOR_JOB_TIMEOUT_MULTIPLIER`.
4. Each following generation derives its limit from the preceding generation after the configured top-tail trim; timed-out records participate as infinity under the documented finite-fallback rule.
5. When smoke is disabled, the user-entered memory, disk, and one-hour timeout baselines stand in for smoke measurements and receive their configured bootstrap multipliers.

## Scenario 9: Build And Inspect The Package Foundation
1. A developer installs the declared development build tools.
2. A PEP 517 frontend builds wheel and sdist from `pyproject.toml`.
3. The artifacts contain the `yadof` namespace, one version value, console entry
   point, versioned software-neutral starter, init/check, explicit workspace/config/
   task loaders, stable job-template framework helpers, packaged local evaluator,
   workspace-explicit recorded-data APIs, standalone local smoke command, and
   authoritative documentation.
4. Artifact inspection rejects the current task/runtime tree, simulator model files,
   jobs, history, checkpoints, caches, and secrets.
5. A clean virtual environment outside the repository installs the wheel without
   repository `PYTHONPATH` and runs help, version, and both document commands.
6. The same commands leave non-writable installed package files unchanged.
7. In an external runtime-capable environment, the installed command initializes
   and checks a generic workspace outside the repository while site-packages is
   non-writable.
8. The generated workspace contains its marker and three user task files but no
   framework `api.py`, parameter class, rawData contract, evaluator, optimizer,
   recorder, or surrogate implementation; installed package hashes remain unchanged.
9. With site-packages still non-writable, the installed smoke command executes the
   generic workflow once; edited failure and short-timeout cases remain isolated in
   workspace jobs/history and still leave installed-package and repository-source
   hashes unchanged.

## Scenario 10: Alternate Two Workspaces In One Process
1. A caller builds or loads the effective config for workspace A.
2. Package defaults are overridden by A's `config.py` and optional temporary values;
   the file itself is not rewritten.
3. Parameter and cost queries freshly compile A's task modules and local helpers,
   then remove their temporary import state.
4. The caller records/queries a same-named job in A, then performs the same operations
   for workspace B; helpers, config, parameters, objectives, manifests, locks,
   archives, and results remain independent.
5. A task/config edit in A is visible on the next call even when its timestamp and
   source size would otherwise permit stale bytecode reuse.
6. Switching back to B returns B's unchanged values, and `sys.path` plus unrelated
   pre-existing `sys.modules` entries are identical to their original state.

## Scenario 11: Initialize And Check A Workspace

1. A user runs `yadof init PATH` on a new or empty directory.
2. Init loads the bundled manifest, finds no target conflicts, writes a sibling
   stage, validates marker/config/parameters/objectives/workflow syntax, then
   publishes the workspace. The marker records versions but no machine path.
3. The user edits `config.py` or task files and repeats init; init confirms the
   complete matching workspace and changes nothing.
4. If an unmarked directory already contains a template target, init prints each
   exact conflict and creates no marker or partial template. If a marked workspace
   is missing a required user file, init reports it but does not recreate it.
5. The user runs `yadof check --workspace PATH`. Check reports structure, marker,
   config, parameter/objective imports, workflow syntax, static rawData, and selected
   backend prerequisites.
6. Check never imports/executes workflow, submits a job, installs a command, repairs
   HTCondor, or mutates the workspace. Missing external prerequisites are actionable
   administrator-facing errors.

## Scenario 12: Prepare And Smoke A Package Workspace Locally

1. A user runs `yadof smoke-test --workspace PATH --mode local` on an unchanged
   initialized generic workspace.
2. The command confirms the task files exactly match the bundled generic starter,
   selects one normalized midpoint individual, and disables timeout.
3. `yadof.evaluate_manager` rejects reserved filename collisions, then copies the
   workspace workflow, any task adapters/assets, package `worker_misc.py`, compact
   effective worker config, and an assigned parameter snapshot into
   `workspace/jobs/<job_name>/`. Submit-side `calc_cost.py` is excluded.
4. The local Python subprocess writes lifecycle metadata and flat rawData. The
   runner validates both, rejects/removes any `cost.json`, and preserves stdout/
   stderr diagnostics.
5. The submit process records raw variables/rawData/metadata below the effective
   workspace record path, freshly loads workspace `calc_cost.py` from the archived
   evidence, derives one cost tuple, and reports success.
6. If task bytes were edited or extra task assets/adapters were added, the CLI
   creates no job until the user repeats with `--real-task`, whose help explicitly
   warns that workflow execution may launch expensive external software.
