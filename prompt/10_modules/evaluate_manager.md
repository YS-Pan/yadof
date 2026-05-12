# Module prompt: evaluate_manager

## Intent
- Bridge normalized optimizer individuals to isolated job folders and real evaluation execution.
- Keep local execution usable today while leaving distributed/HTCondor as an explicit future backend.
- Treat every individual independently so one failed preparation, workflow run, timeout, or recording step does not stop the generation.

## Functionalities
- `api.evaluate_population()` selects the configured backend and returns cost tuples to `optimize`.
- Local mode prepares a job, runs `workflow.py`, records the result through `recorded_data.api`, and converts failures to `inf` cost rows.
- `job_files.prepare_job()` copies job template files, denormalizes variables via `job_template.api`, writes `job_input.json`, and records `job_static_hash` in metadata.
- `local_runner.run_local_job()` launches the copied workflow in the job directory, enforces timeout, captures stdout/stderr tails, and discovers flat `rawData/*.npz` outputs.
- `recorded_data_client.record_result()` adapts `JobResult` to supported `recorded_data.api` functions and retrieves dynamically computed costs when possible.
- `types.py` defines immutable `JobSpec` and `JobResult` records for internal handoff.

## I/O Format
- Input: `population[individual][normalized_variable]`.
- Prepared job input: `job_input.json` with `job_name`, `normalized_variables`, and `unnormalized_variables`.
- Job metadata: `metadata.json` and `metaData.json`, including status, engine, static hash, variables, timing, and failure details.
- Raw outputs: top-level `.npz` files under each job's `rawData/` directory.
- Public output: `population[individual][objective_cost]`, with `inf` rows for failures whose objective width cannot be recovered.

## Non-Obvious Techniques
- `calc_cost.py` is excluded from job copies. Jobs generate rawData only; cost is derived after recording.
- `hfss_com.py` is excluded from current job copies because this round uses `test_com.py`; future simulator adapters should be added deliberately.
- `job_static_hash` excludes `rawData`, metadata, `job_input.json`, and other runtime files so it reflects static task definition, not individual values.
- Failure recording is best effort. If recording a failure also fails, generation evaluation still continues.
- Distributed mode should reuse the same status interpretation and recording path instead of inventing a second result schema.

## Mutability Profile
- Local execution details and distributed backend wiring may change.
- Job metadata and `JobResult` shape should change cautiously because recorded-data ingestion and tests consume them.
- Template-copy exclusions must stay aligned with the rawData-first and no-cost-file contract.
