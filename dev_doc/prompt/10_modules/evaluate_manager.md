# Module prompt: evaluate_manager

## Intent
- Bridge normalized optimizer individuals to isolated job folders and real evaluation execution.
- Keep local execution usable today while leaving distributed/HTCondor as an explicit future backend.
- Treat every individual independently so one failed preparation, workflow run, timeout, or recording step does not stop the generation.

## Functionalities
- `api.evaluate_population()` selects the configured backend and returns cost tuples to `optimize`.
- Local mode prepares a job, runs `workflow.py`, reads the job-local `individual_metadata.json`, records the result through `recorded_data.api`, and converts failures to `inf` cost rows.
- `job_files.prepare_job()` copies job template files, denormalizes variables via `job_template.api`, writes `job_input.json` with run/generation context, and records `job_static_hash` in submit-side metadata.
- `local_runner.run_local_job()` launches the copied workflow in the job directory, enforces timeout, captures stdout/stderr tails, reads workflow-owned lifecycle metadata, and discovers flat `rawData/*.npz` outputs.
- `recorded_data_client.record_result()` adapts `JobResult` to supported `recorded_data.api` functions and retrieves dynamically computed costs when possible.
- `types.py` defines immutable `JobSpec` and `JobResult` records for internal handoff.

## I/O Format
- Input: `population[individual][normalized_variable]`.
- Prepared job input: `job_input.json` with `job_name`, `normalized_variables`, `unnormalized_variables`, and `evaluation_context` containing `run_id`, `optimization_index`, `generation_index`, and `population_index` when available.
- Job metadata: `metadata.json` and `metaData.json` contain submit-side status, engine, static hash, runner diagnostics, and merged workflow lifecycle fields. The workflow-owned source for `started_at` and `ended_at` is `individual_metadata.json`.
- Raw outputs: top-level `.npz` files under each job's `rawData/` directory.
- Public output: `population[individual][objective_cost]`, with `inf` rows for failures whose objective width cannot be recovered.

## Non-Obvious Techniques
- `calc_cost.py` is excluded from job copies. Jobs generate rawData only; cost is derived after recording.
- `hfss_com.py` is excluded from current job copies because this round uses `test_com.py`; future simulator adapters should be added deliberately.
- `job_static_hash` excludes `rawData`, metadata, `job_input.json`, and other runtime files so it reflects static task definition, not individual values.
- `created_at` is not recorded. If job creation time is needed, infer it from the time-based job folder name.
- `evaluate_manager` adds runner diagnostics such as return code and stdout/stderr tails, while preserving workflow-written `started_at`/`ended_at`.
- Individual records carry `optimization_index` and `generation_index` from optimizer context so downstream tools can group evaluations without joining through optimization metadata first.
- Failure recording is best effort. If recording a failure also fails, generation evaluation still continues.
- Distributed mode should reuse the same status interpretation and recording path instead of inventing a second result schema.

## Mutability Profile
- Local execution details and distributed backend wiring may change.
- Job metadata and `JobResult` shape should change cautiously because recorded-data ingestion and tests consume them.
- Template-copy exclusions must stay aligned with the rawData-first and no-cost-file contract.
