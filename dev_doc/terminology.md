# Project-Specific Terminology

Only terms that need project context are listed here.

| Term | Meaning In This Project |
|---|---|
| `expensive evaluation` | A real workflow run that converts task variables into rawData by calling a simulator, custom Python, or a multi-step task workflow. It does not create authoritative cost files. |
| `rawData` | Task-owned evidence produced by `workflow.py`, usually one or more flat `rawData/*.npz` files. It is the durable source for later cost calculation and surrogate training. |
| `cost` | Dynamic objective value tuple calculated from rawData by the current `job_template/calc_cost.py`. Cost is returned to callers but is not stored as durable source truth. |
| `normalized_variables` | Optimizer-space values, usually floats in `[0, 1]`. Historical normalized values are calculated on demand by `recorded_data` from saved raw variables and current parameter ranges. |
| `unnormalized_variables` | Task-space/raw variable values used by the workflow. These are stored durably once per individual in recorded data. |
| `PARAMETERS` | The task-owned parameter definitions in `project/job_template/parameters_constraints.py`, exposed through `job_template.api` for variable names, ranges, units, normalization, and denormalization. |
| `workflow.py` | The active task file that runs an expensive evaluation and writes rawData plus job-local lifecycle metadata. It must not write final costs. |
| `calc_cost.py` | The active task file that interprets rawData into current objective costs and optional rawData importance weights for surrogate training. It is not copied into prepared job folders. |
| `key config` | The short user-editable `project/config.py` file for routine campaign settings. It contains constants only and is copied into every prepared job folder. |
| `full config` | The grouped `project/config_all.py` default surface imported by runtime modules. It imports matching overrides from `config.py` and is also copied into every prepared job folder. |
| `local mode` | Evaluation backend where `evaluate_manager` runs prepared jobs as local subprocesses. It is the default mode for tests and first debugging passes. |
| `distributed mode` | Evaluation backend where `evaluate_manager` submits prepared jobs to HTCondor while preserving the same job folder and recording contract as local mode. |
| `GPSAF` | The surrogate-assisted optimizer framing used by `project.optimize`, including alpha/beta/gamma surrogate pressure controls and real-evaluation validation of selected candidates. |
| `individual` | One optimizer candidate after it has been turned into a real evaluation job. In code this is usually represented by a job folder and later by one `indMeta.jsonl` row. |
| `individual_metadata.json` | A job-local JSON file written by `workflow.py`. It is the source of truth for an individual's `started_at`, `ended_at`, workflow status, and run/generation context that the workflow can see. |
| `indMeta.jsonl` | Append-only recorded-data stream with one compact row per individual. It stores raw variables once, archived rawData member names, compact rawData metadata, workflow timing, status, and run/generation identifiers. |
| `rawData.npz` | A zip-based archive despite the `.npz` suffix. Members are named `job_name/file.npz` and store the actual rawData files produced by jobs. |
| `rawdata_metadata` | Metadata extracted from each rawData `.npz` for quick inspection in `indMeta.jsonl`. It is scrubbed so repeated variable vectors do not appear once per rawData file. |
| `job_static_hash` | A hash of static files copied into a prepared job. It excludes runtime files and per-individual values, so it marks task-definition changes rather than candidate changes. |
| `HTCondor runner` | The `project/evaluate_manager/condor_runner.py` backend that writes `job.sub`, submits prepared jobs with direct `workflow.py` executable transfer, waits for job-local outputs, and returns `JobResult` objects for the same recording path used by local mode. It does not modify or repair the installed HTCondor pool. |
| `run_id` | String identifier for one optimizer run created by `optimize.api.run_generations()` or direct single-generation calls. |
| `optimization_index` | Numeric ordinal for an optimization run. It is stored on each individual and in generation-level metadata. |
| `generation_index` | Numeric generation number inside an optimization run. It is stored on each individual and in generation-level metadata. |
| `population_index` | Zero-based position of an individual inside the evaluated population sent to `evaluate_manager`. |
| `dev_doc` | Documentation home for project specification, architecture views, generative blueprints, reference ancestry, terminology, change records, and obsolete notes. |
| `user_doc` | User-facing documentation home for preparing optimization tasks, choosing adapter files, writing `workflow.py` and `calc_cost.py`, editing run config, smoke testing, and launching optimization. Reading `dev_doc` includes `user_doc`, but reading `user_doc` alone does not include `dev_doc`. |
| `blueprint` | A generative module document under `dev_doc/blueprints/`. Its goal is to let an AI recreate equivalent behavior from the document, not merely describe the current source file. |
| `change_records` | Time-named documentation records under `dev_doc/change_records/` that explain what changed and why. They are not read by default during normal context gathering. |
| `NSGA-III reference direction` | A target direction in objective space used by pymoo NSGA-III survival to keep multi-objective candidates spread across tradeoff regions. The optimizer records the method, partition count, and direction count in diagnostics. |
| `surrogate exploration quota` | A small fraction of real-evaluation candidates reserved from baseline offspring or random refill during surrogate-assisted generations. These candidates bypass surrogate-predicted selection so a tradeoff branch cannot be fully starved by surrogate bias. |
| `surrogate historical error audit` | The surrogate's comparison between true historical costs and costs from model-predicted rawData. It feeds diagnostics and must not be forced to zero by substituting true costs for predictions. |
| `surrogate cost interval` | The optimizer-facing `(lower, upper)` range returned with each surrogate-predicted objective. In the current contract it is exactly the per-objective minimum and maximum cost across deep-ensemble member predictions. It does not use historical error calibration or fixed floors. |
| `rawData importance weights` | Task-owned per-rawData-array weights returned by `job_template.api` to emphasize objective-relevant rawData windows during surrogate full-field training while retaining a positive weight floor outside those windows. |
| `com_lib` | Non-core adapter staging/reference library under `project/com_lib/`. Files here are not copied or imported by active jobs; users copy a needed com file into `project/job_template/` before a workflow can use it. Adapter files may also have task-local active copies in `job_template`. |
| `staggered surrogate training` | Surrogate schedule where GPSAF uses the latest completed surrogate state to choose the next real-evaluation population, submits real jobs first, then trains a new surrogate on the submit side while the cluster is busy. The default lag rule allows one or two generations of lag and blocks before a third. |
