# Module blueprint: evaluate_manager

## Intent
- Bridge normalized optimizer individuals to isolated job folders and real evaluation execution.
- Keep local execution usable by default while supporting distributed execution through an explicit HTCondor backend.
- Treat every individual independently so one failed preparation, workflow run, timeout, or recording step does not stop the generation.

## Historical Lineage
- Prepared job folders, generation evaluation, status collection, and failure handling descend from the fanyufei prepare/evaluate lineage.
- Optional HTCondor submission and polling behavior descend from the older combined-project lineage and the current `reference/htcondor_windows_debug_reference.md` notes.
- Current local and distributed backends share the v3 rawData-first recording path rather than preserving separate legacy result schemas.

## Functionalities
- `api.evaluate_population()` selects the configured backend (`local` or `distributed`) and returns cost tuples to `optimize`.
- Local mode prepares a job, runs `workflow.py`, reads the job-local `individual_metadata.json`, records the result through `recorded_data.api`, and converts failures to `inf` cost rows. When `LOCAL_EVALUATION_MAX_WORKERS > 1`, multiple independent individuals run concurrently while preserving output order.
- Distributed mode prepares all jobs, writes HTCondor submit files, submits the prepared job-local `workflow.py` directly as the transferred executable, runs an optional submit-side callback after all prepared jobs are submitted, waits for job-local outputs, records results through the same finalization path, and converts failed/timeout rows to `inf`.
- `job_files.prepare_job()` copies job template files through `job_template.api`, copies both submit-side config files (`config.py` and `config_all.py`) into the job folder, denormalizes variables via `job_template.api`, writes `job_input.json` with run/generation context, and records `job_static_hash` in submit-side metadata.
- `local_runner.run_local_job()` launches the copied workflow in the job directory, enforces timeout, captures stdout/stderr tails, reads workflow-owned lifecycle metadata, and discovers flat `rawData/*.npz` outputs.
- `condor_runner.run_condor_jobs()` generates `job.sub`, calls `condor_submit`, captures submit diagnostics, polls job outputs/`condor.log`, queries hold details for held jobs, extracts Condor return-value/log tails when available, best-effort removes timed-out cluster ids, and collects `JobResult` objects.
- `job_result.py` provides shared helpers for reading/writing job metadata, discovering rawData files, promoting workflow metadata, and constructing `JobResult`.
- `recorded_data_client.record_result()` adapts `JobResult` to supported `recorded_data.api` functions and retrieves dynamically computed costs when possible.
- `types.py` defines immutable `JobSpec` and `JobResult` records for internal handoff.

## I/O Format
- Input: `population[individual][normalized_variable]`.
- Prepared job input: `job_input.json` with `job_name`, `normalized_variables`, `unnormalized_variables`, and `evaluation_context` containing `run_id`, `optimization_index`, `generation_index`, and `population_index` when available.
- Job metadata: `metadata.json` and `metaData.json` contain submit-side status, engine, static hash, runner diagnostics, and merged workflow lifecycle fields. The workflow-owned source for `started_at` and `ended_at` is `individual_metadata.json`.
- Raw outputs: top-level `.npz` files under each job's `rawData/` directory.
- HTCondor submit file: `job.sub` with `executable = workflow.py`, no workflow argument line, `transfer_executable = True`, and a quoted whitespace-separated environment string for sandboxed Windows profile/temp variables and HFSS runtime defaults. `transfer_output_files` is intentionally omitted so HTCondor returns generated files, including PyAEDT-created `batch.log` when present, without holding the job if optional files are absent.
- Public output: `population[individual][objective_cost]`, with `inf` rows for failures whose objective width cannot be recovered.

## Non-Obvious Techniques
- `calc_cost.py` is excluded from job copies. Jobs generate rawData only; cost is derived after recording.
- `calc_cost.py` is excluded from job copies, while active adapter files already placed in `job_template` are copied because workflow execution needs them in the job folder. The current active adapter is `hfss_com.py`.
- `job_static_hash` excludes `rawData`, metadata, `job_input.json`, and other runtime files so it reflects static task definition, not individual values.
- `created_at` is not recorded. If job creation time is needed, infer it from the time-based job folder name.
- `evaluate_manager` adds runner diagnostics such as return code, stdout/stderr tails, Condor log tails, and optional `batch.log` tails, while preserving workflow-written `started_at`/`ended_at`.
- Individual records carry `optimization_index` and `generation_index` from optimizer context so downstream tools can group evaluations without joining through optimization metadata first.
- Failure recording is best effort. If recording a failure also fails, generation evaluation still continues.
- Local parallelism is at the individual/job level. Each worker still executes prepare -> run -> record for one candidate, while `recorded_data` locks serialize durable writes.
- Distributed mode reuses the same result schema and recording path instead of inventing a second result schema.
- HTCondor submit failures are treated as evaluation failures. The project captures diagnostics but does not attempt to repair daemon, pool, credential, or topology problems in the installed HTCondor environment.
- The Windows HTCondor submit pattern uses direct `workflow.py` submission with `transfer_executable = True`; the earlier interpreter-as-executable pattern is intentionally not supported. Keep `run_as_owner = False` and `load_profile = True` unless the user deliberately changes identity policy.
- `YADOF_PROGRESS=1` enables coarse console progress for long distributed runs without making public API calls noisy by default.

- `after_jobs_submitted` callbacks are submit-side hooks. In distributed mode `condor_runner` calls the hook after all successful submissions and before polling; callback failures are logged but do not cancel already-submitted jobs.

## Mutability Profile
- Local execution details and HTCondor backend wiring may change.
- Job metadata and `JobResult` shape should change cautiously because recorded-data ingestion and tests consume them.
- Template-copy exclusions must stay aligned with the rawData-first and no-cost-file contract.
