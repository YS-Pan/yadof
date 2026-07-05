# Module blueprint: config

## Intent
- Provide a small shared configuration surface for cross-module settings that are not task-specific source code.
- Keep problem shape and objective schema out of config; those belong to `job_template.api`.
- Make local/default behavior explicit while leaving optional distributed and surrogate-assisted tuning paths visible.

## Functionalities
- Defines root paths such as `PROJECT_ROOT`, `JOBS_DIR`, and `SURROGATE_CHECKPOINT_DIR`.
- Selects `EVALUATION_MODE`.
- Defines local evaluation worker count for parallel-safe local workflows.
- Defines HTCondor command/resource/submit defaults for distributed evaluation.
- Defines optimizer population, random seed, NSGA-III reference-direction controls, pymoo operator parameters, duplicate-key rounding, and refill behavior.
- Defines surrogate model, torch device selection, conditional-INR training, target scaling, task-owned rawData importance weighting, stochastic training query limits, and error hyperparameters.
- Defines GPSAF surrogate assistance controls: `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, `OPTIMIZE_SURROGATE_GAMMA`, and `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION`.

## I/O Format
- Config values are imported directly by modules that need them.
- Paths are `Path` objects rooted in `project/`.
- Numeric controls should be simple Python scalars.
- Local and HTCondor controls are simple strings, numbers, and booleans such as `EVALUATION_TIMEOUT_SEC`, `LOCAL_EVALUATION_MAX_WORKERS`, `HTCONDOR_SUBMIT_EXE`, `HTCONDOR_PYTHON_EXE`, `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, `HTCONDOR_ENVIRONMENT`, `HTCONDOR_LOAD_PROFILE`, `HTCONDOR_RUN_AS_OWNER`, and `HTCONDOR_REQUIREMENTS`.

## Non-Obvious Techniques
- Setting `OPTIMIZE_SURROGATE_ALPHA = 1` and `OPTIMIZE_SURROGATE_BETA = 0` keeps the GPSAF entry point available while disabling surrogate calls.
- Variable count and objective count are deliberately absent from config and resolved through `job_template.api`.
- `JOBS_DIR` is the submit-side runtime staging location for prepared job folders. Worker-side scratch placement is an HTCondor `EXECUTE` setting, not a `JOBS_DIR` setting.
- When requiring RAM-disk workers, `HTCONDOR_REQUIREMENTS` can match the worker-advertised `YADOF_RAMDISK` attribute written by the pool setup tools.
- `HTCONDOR_PYTHON_EXE` must be an executable path that exists on every worker that can match the job, such as the shared Conda environment's `python.exe`.
- `EVALUATION_TIMEOUT_SEC` is the generation-level wait budget for distributed evaluation, not just a single HFSS solve timeout. Large populations submitted in waves need a value large enough for the full generation to drain.
- `HTCONDOR_REQUEST_CPUS` should stay aligned with workflow-side `YADOF_HFSS_JOB_CPUCORE` in `HTCONDOR_ENVIRONMENT` so HFSS does not consume more cores than Condor reserved for the slot.
- `HTCONDOR_REQUEST_MEMORY` is a scheduler reservation. It should be high enough for AEDT startup and solve memory so the pool does not overpack workers.
- `EVALUATION_MODE` remains `local` by default so the project does not require HTCondor for normal tests or first-run debugging.
- `LOCAL_EVALUATION_MAX_WORKERS` defaults to 1 to preserve simulator safety; raising it enables local per-individual subprocess parallelism for workflows that can run concurrently. Local evaluation reloads `project/config.py` when this value is read, so edits made during a run can take effect at the next generation/evaluation call.
- HTCondor command settings may be overridden by matching legacy environment variables such as `CONDOR_SUBMIT_EXE`, `CONDOR_POLL_SEC`, `CONDOR_REQUEST_CPUS`, `CONDOR_REQUEST_MEMORY`, and `CONDOR_REQUEST_DISK`.
- The default HTCondor environment follows the Windows debug reference and redirects profile/temp paths into job-local directories.
- `SURROGATE_TORCH_DEVICE = "auto"` prefers CUDA, then XPU, then CPU; tests may force CPU and smaller INR dimensions for speed.
- `SURROGATE_RAWDATA_IMPORTANCE_FLOOR` and `SURROGATE_RAWDATA_IMPORTANCE_BOOST` are passed to task-owned rawData importance hooks; they do not remove full-field training coverage. `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` caps how many high-dimensional rawData query points are sampled per training step when fields are very large; scalar and 1D rawData slots are still always included, and prediction, reconstruction, checkpoints, and historical error audits still use the full query table.
- `OPTIMIZE_NSGA3_REF_DIR_METHOD` and `OPTIMIZE_NSGA3_PARTITIONS` tune NSGA-III reference directions without reintroducing an algorithm-selection switch.
- `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` reserves real-evaluation candidates that bypass surrogate selection so surrogate bias cannot fully starve a tradeoff branch.

## Mutability Profile
- Users may tune config often during experiments.
- Avoid adding task-specific workflow logic or cost definitions here.
- When a new config value affects stored history interpretation, document the consequence in blueprint and architecture docs.
