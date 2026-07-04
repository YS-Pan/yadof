# Project-Specific Terminology

Only terms that need project context are listed here.

| Term | Meaning In This Project |
|---|---|
| `individual` | One optimizer candidate after it has been turned into a real evaluation job. In code this is usually represented by a job folder and later by one `indMeta.jsonl` row. |
| `individual_metadata.json` | A job-local JSON file written by `workflow.py`. It is the source of truth for an individual's `started_at`, `ended_at`, workflow status, and run/generation context that the workflow can see. |
| `indMeta.jsonl` | Append-only recorded-data stream with one compact row per individual. It stores raw variables once, archived rawData member names, compact rawData metadata, workflow timing, status, and run/generation identifiers. |
| `rawData.npz` | A zip-based archive despite the `.npz` suffix. Members are named `job_name/file.npz` and store the actual rawData files produced by jobs. |
| `rawdata_metadata` | Metadata extracted from each rawData `.npz` for quick inspection in `indMeta.jsonl`. It is scrubbed so repeated variable vectors do not appear once per rawData file. |
| `job_static_hash` | A hash of static files copied into a prepared job. It excludes runtime files and per-individual values, so it marks task-definition changes rather than candidate changes. |
| `HTCondor runner` | The `project/evaluate_manager/condor_runner.py` backend that writes `job.sub`, submits prepared jobs with `condor_submit`, waits for job-local outputs, and returns `JobResult` objects for the same recording path used by local mode. It does not modify or repair the installed HTCondor pool. |
| `run_id` | String identifier for one optimizer run created by `optimize.api.run_generations()` or direct single-generation calls. |
| `optimization_index` | Numeric ordinal for an optimization run. It is stored on each individual and in generation-level metadata. |
| `generation_index` | Numeric generation number inside an optimization run. It is stored on each individual and in generation-level metadata. |
| `population_index` | Zero-based position of an individual inside the evaluated population sent to `evaluate_manager`. |
| `dev_doc` | Documentation home for project specification, architecture views, generative blueprints, reference ancestry, terminology, change records, and obsolete notes. |
| `blueprint` | A generative module document under `dev_doc/blueprints/`. Its goal is to let an AI recreate equivalent behavior from the document, not merely describe the current source file. |
| `change_records` | Time-named documentation records under `dev_doc/change_records/` that explain what changed and why. They are not read by default during normal context gathering. |
| `NSGA-III reference direction` | A target direction in objective space used by pymoo NSGA-III survival to keep multi-objective candidates spread across tradeoff regions. The optimizer records the method, partition count, and direction count in diagnostics. |
| `surrogate exploration quota` | A small fraction of real-evaluation candidates reserved from baseline offspring or random refill during surrogate-assisted generations. These candidates bypass surrogate-predicted selection so a tradeoff branch cannot be fully starved by surrogate bias. |
| `surrogate historical error audit` | The surrogate's comparison between true historical costs and costs from model-predicted rawData. It feeds diagnostics and must not be forced to zero by substituting true costs for predictions. |
| `surrogate cost interval` | The optimizer-facing `(lower, upper)` range returned with each surrogate-predicted objective. In the current contract it is exactly the per-objective minimum and maximum cost across deep-ensemble member predictions. It does not use historical error calibration or fixed floors. |
| `rawData importance weights` | Task-owned per-rawData-array weights returned by `job_template.api` to emphasize objective-relevant rawData windows during surrogate full-field training while retaining a positive weight floor outside those windows. |
| `com_lib` | Non-core adapter staging/reference library under `project/com_lib/`. Files here are not copied or imported by active jobs; users copy a needed com file into `project/job_template/` before a workflow can use it. The current HFSS adapter has both a reference copy in `com_lib` and an active copy in `job_template`. |
| `Metal_recon_ant` | Historical/example HFSS task name, not a framework-fixed simulation filename. Each optimization task may use a different simulator/model file name, file format, or no `.aedt` file at all; the task-specific `workflow.py` decides which rawData files are produced, and `calc_cost.py` decides which rawData signals matter. |
