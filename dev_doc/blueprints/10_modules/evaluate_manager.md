# Module blueprint: evaluate_manager

## Intent
- Bridge normalized optimizer individuals to isolated job folders and real evaluation execution.
- Keep local execution usable by default while supporting distributed execution through an explicit HTCondor backend.
- Treat every individual independently so one failed preparation, workflow run, timeout, or recording step does not stop the generation.

## Historical Lineage
- Prepared job folders, generation evaluation, status collection, and failure handling descend from the fanyufei prepare/evaluate lineage.
- Optional HTCondor submission and polling behavior descend from the older combined-project lineage and the current `admin_tool/htcondor_doc/` notes.
- Current local and distributed backends share the rawData-first recording path rather than preserving separate result schemas.

## Functionalities
- `yadof.evaluate_manager.api.evaluate_population(workspace, ...)` fresh-loads the
  workspace config and supports the packaged local backend. It returns objective
  tuples in input order; `run_smoke_test(workspace, ...)` runs exactly one midpoint
  individual without a generation or per-job timeout.
- Packaged local mode prepares a workspace job, runs `workflow.py`, reads job-local
  lifecycle metadata, validates flat rawData, calculates cost through the current
  workspace `calc_cost.py`, and converts per-individual failures to correctly sized
  `inf` rows. Before deriving cost it records every completed/error/timeout result
  best effort through `yadof.recorded_data`. When `LOCAL_EVALUATION_MAX_WORKERS > 1`,
  independent individuals run concurrently.
- `project.evaluate_manager` remains the transitional source optimizer/recording/
  distributed path. Its local behavior still records through `recorded_data.api`
  until those consumers move; it is not imported or aliased by the package API.
- Distributed mode prepares all jobs, writes HTCondor submit files, submits the prepared job-local `workflow.py` directly as the transferred executable, runs an optional submit-side callback after all prepared jobs are submitted, waits for job-local outputs, records results through the same finalization path, and converts failed/timeout rows to `inf`.
- `yadof.evaluate_manager.job_files.prepare_job()` copies all non-runtime workspace
  task files/assets except submit-side `calc_cost.py`, rejects case-insensitive
  collisions with package-reserved `worker_misc.py` and
  `yadof_worker_config.json`, materializes assigned parameters through the package
  job-template API, copies package worker support, writes only a compact effective
  worker config/provenance summary, and records `job_static_hash`.
- Packaged `local_runner.run_local_job()` launches the copied workflow in the job
  directory with bytecode writes disabled, enforces process-tree timeout, captures
  stdout/stderr tails, reads workflow-owned lifecycle metadata, validates flat
  `rawData/*.npz`, and rejects/removes a workflow-created `cost.json`.
- The source `project.evaluate_manager` job/runner/recording behavior remains for
  current optimizer and HTCondor callers until their later ordered migrations.
- `resource_requests.py` derives a per-job memory/disk request from prior recorded
  HTCondor measurements while preserving the user-selected CPU request. It uses
  unindexed distributed smoke records for generation zero and the same run's
  preceding generation thereafter.
- `resource_retries.py` owns the removable yadof-side retry policy for standard
  HTCondor memory/disk resource holds: classify numeric hold codes, keep independent
  retry counts, double only the exhausted request, record attempt history, and clear
  stale attempt outputs before a fresh cluster is submitted.
- `time_limits.py` derives `allowed_execute_duration` from the configured fixed baseline or from smoke/preceding-generation execution durations with high-tail trimming and timeout-as-infinity handling.
- `condor_runner.run_condor_jobs()` generates `job.sub`, calls `condor_submit`, captures submit diagnostics, polls job outputs/`condor.log`, queries hold details for held jobs, delegates memory/disk retry decisions and cleanup to `resource_retries.py`, submits fresh clusters when requested, queries final Condor ClassAd resource/time usage when available, extracts Condor return-value/log tails, removes held or generation-timeout cluster ids, and collects `JobResult` objects while isolating per-job collection failures.
- `job_result.py` provides shared helpers for reading/writing job metadata, discovering rawData files, promoting workflow metadata, and constructing `JobResult`.
- Packaged `recorded_data_client.record_result(workspace, result)` maps `JobResult`
  directly to `yadof.recorded_data.api` and retrieves that exact job's dynamically
  computed cost. The transitional source client retains its old adaptive bridge.
- `types.py` defines immutable `JobSpec` and `JobResult` records for internal handoff.

## I/O Format
- Input: `population[individual][normalized_variable]`.
- Prepared job parameter input: `parameters_constraints.py` with name, ranges, unit,
  assigned `normalized_value`, assigned raw `value`, and constraints. Submit-side
  metadata carries `run_id`, `optimization_index`, `generation_index`, and
  `population_index` when available.
- Job metadata: `metadata.json` and `metaData.json` contain submit-side status, engine, static hash, runner diagnostics, calculated resource-request source/values, returned Condor memory/disk/CPU measurements when available, and merged workflow lifecycle fields. The workflow-owned source for `started_at` and `ended_at` is `individual_metadata.json`.
- Packaged local metadata additionally carries installed `yadof_version`, a
  `workspace_identity` with resolved root and portable marker, and an
  `effective_config_summary` limited to mode, timeout, and local worker count with
  each value's source. The same subset is copied as `yadof_worker_config.json`.
- Raw outputs: top-level `.npz` files under each job's `rawData/` directory.
- HTCondor submit file: `job.sub` with `executable = workflow.py`, no workflow argument line, `transfer_executable = True`, one concrete `request_memory`/`request_disk`, no Condor-native resource retry directives, a normal-job `allowed_execute_duration`, and a quoted whitespace-separated environment string composed from generic sandboxed Windows profile/temp entries plus active `config/specific/` contributions. Smoke omits the time limit. `transfer_output_files` is intentionally omitted so HTCondor returns generated files without holding the job if optional files are absent.
- Public output: `population[individual][objective_cost]`, with `inf` rows for failures whose objective width cannot be recovered.

## Non-Obvious Techniques
- `calc_cost.py` is excluded from every job copy. Jobs generate rawData only; the
  transitional source path derives cost after recording.
- In the package local path, validated output is archived first and cost is then
  derived from the workspace archive using the current task policy.
- Active task-local adapters and arbitrary assets are recursively copied because a
  workflow may use one or several programs. Package worker support wins no collision:
  a reserved-name task file is rejected before any job directory is created.
- `job_static_hash` excludes rawData, metadata, and other runtime files. It hashes a
  definition-only parameter signature so assigned values do not affect the hash,
  while name, ranges, unit, and constraints do.
- `created_at` is not recorded. If job creation time is needed, infer it from the time-based job folder name.
- `evaluate_manager` adds runner diagnostics such as return code, stdout/stderr tails, Condor log tails, and optional `batch.log` tails, while preserving workflow-written `started_at`/`ended_at`.
- Individual records carry `optimization_index` and `generation_index` from optimizer context so downstream tools can group evaluations without joining through optimization metadata first.
- Failure recording is best effort. If recording a failure also fails, generation evaluation still continues.
- Packaged local cost-calculation failure is per-individual and becomes metadata plus
  `inf`; static task/config validation and reserved-name collisions fail before
  batch execution because they affect every individual.
- Local parallelism is at the individual/job level. Packaged workers execute
  prepare -> run -> record -> dynamic cost; workspace-keyed process/file locks
  serialize each history's durable writes without sharing records across workspaces.
- Distributed mode reuses the same result schema and recording path instead of inventing a second result schema.
- The adaptive resource controller never rewrites source config. It treats
  `HTCONDOR_REQUEST_MEMORY` and `HTCONDOR_REQUEST_DISK` as safe fallbacks when a
  distributed smoke test or previous generation has no usable ClassAd measurement.
- The adaptive time controller also never rewrites config. It records the effective
  limit/source/sample count in job metadata, uses Condor execution duration when
  available, and falls back to workflow timestamps. Duration hold codes 46/47 are
  recorded as `timeout`, removed from the queue, and never retried.
- All memory/disk request changes are yadof-side policy. Numeric hold code 34 with
  subcode 102 or 104 enters the removable `resource_retries.py` state machine. The
  runner removes the old cluster before resetting attempt outputs and resubmitting
  the same job with only memory or disk doubled. `YADOF_RESOURCE_RETRY_DOUBLINGS`
  limits each resource independently; timeout/workflow/submit failures and other
  holds are terminal and never use this retry path. All attempts share the original
  generation wait deadline.
- In distributed mode, returned nested `rawData/*.npz` files are the primary rawData path. `rawData_outputs.zip` is a legacy/fallback transfer archive and a bad fallback zip must become per-job diagnostics rather than a generation-wide exception.
- HTCondor submit failures are treated as evaluation failures. The project captures diagnostics but does not attempt to repair daemon, pool, credential, or topology problems in the installed HTCondor environment.
- The Windows HTCondor submit pattern uses direct `workflow.py` submission with `transfer_executable = True`; the earlier interpreter-as-executable pattern is intentionally not supported. Keep `run_as_owner = False` and `load_profile = True`. `run_as_owner=True` is not a deployable project fix because office/personal workstations have different owners and any machine may submit or execute jobs.
- `YADOF_PROGRESS=1` enables coarse console progress for long distributed runs without making public API calls noisy by default.

- `after_jobs_submitted` callbacks are submit-side hooks. In distributed mode `condor_runner` calls the hook after all successful submissions and before polling; callback failures are logged but do not cancel already-submitted jobs.

## Mutability Profile
- `src/yadof/evaluate_manager` owns the stable package-era local contract;
  `project/evaluate_manager` retains transitional recording/distributed code.
- Local execution details and HTCondor backend wiring may change.
- Job metadata and `JobResult` shape should change cautiously because recorded-data ingestion and tests consume them.
- Template-copy exclusions must stay aligned with the rawData-first and no-cost-file contract.
