# Module blueprint: config

## Intent
- Provide a two-layer shared configuration surface for cross-module run settings that are not task-specific source code.
- Keep `project/config.py` small enough for routine campaign edits while preserving a full grouped reference in `project/config_all.py`.
- Keep problem shape and objective schema out of config; those belong to `job_template.api`.

## Historical Lineage
- Optimizer and evaluation launch settings descend from fanyufei-style `optConfig` concepts.
- Surrogate and generation-plan controls descend from shorten-style experiment configuration.
- Current config keeps task shape and objective semantics out of global settings; those belong to `job_template.api`.

## Functionalities
- `project/config.py` defines only key settings users are likely to edit for a new optimization campaign. It must contain settings only and no functions.
- `project/config_all.py` imports `config.py`, groups all known defaults by area, and uses matching names from `config.py` as overrides.
- Defines derived root paths such as `PROJECT_ROOT`, `JOBS_DIR`, and `SURROGATE_CHECKPOINT_DIR` in the full config.
- Selects `EVALUATION_MODE` and timeout behavior.
- Defines local evaluation worker count for parallel-safe local workflows.
- Defines HTCondor command/resource/submit defaults for distributed evaluation.
- Defines workflow-side HFSS defaults such as `HFSS_JOB_CPUCORE`, `HFSS_PARALLEL_TASKS`, and `HFSS_NON_GRAPHICAL`.
- Defines optimizer population, random seed, NSGA-III reference-direction controls, pymoo operator parameters, duplicate-key rounding, and refill behavior.
- Defines surrogate model, torch device selection, conditional-INR training, target scaling, task-owned rawData importance weighting, stochastic training query limits, and error hyperparameters.
- Defines GPSAF surrogate assistance controls: `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, `OPTIMIZE_SURROGATE_GAMMA`, `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION`, and `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG`.

## I/O Format
- Config values are imported directly by modules that need them. Runtime modules should import `project.config_all` so they see the full default surface plus key overrides.
- `config.py` and `config_all.py` contain Python constants only. Do not add helper functions, environment parsers, task logic, or cost/workflow logic to either file.
- Paths are `Path` objects rooted in `project/` when they are derived in `config_all.py`.
- Numeric controls should be simple Python scalars.
- Local and HTCondor controls are simple strings, numbers, and booleans such as `EVALUATION_TIMEOUT_SEC`, `LOCAL_EVALUATION_MAX_WORKERS`, `HTCONDOR_SUBMIT_EXE`, `HTCONDOR_PYTHON_EXE`, `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, `HTCONDOR_ENVIRONMENT`, `HTCONDOR_LOAD_PROFILE`, `HTCONDOR_RUN_AS_OWNER`, and `HTCONDOR_REQUIREMENTS`.

## Non-Obvious Techniques
- `project/config.py` is intentionally short. The current key surface includes evaluation mode/timeout, HTCondor Python and resources, HFSS core/runtime defaults, and population size.
- `project/config_all.py` is the compatibility and discovery layer. Adding a new cross-module setting usually means adding it there first, then deciding whether it is important enough to expose in `config.py`.
- `evaluate_manager` copies both config files into every prepared job folder so submitted jobs keep both the key campaign settings and full default context.
- `workflow.py` reads the copied job-local `config.py` for HFSS defaults, then allows HTCondor environment variables such as `YADOF_HFSS_JOB_CPUCORE` to override runtime values.
- The default HTCondor environment follows quoted, whitespace-separated HTCondor syntax. Do not use semicolon-separated entries in the quoted environment string.
- `HTCONDOR_REQUEST_CPUS` should stay aligned with `HFSS_JOB_CPUCORE` so HFSS does not consume more cores than Condor reserved for the slot.
- Setting `OPTIMIZE_SURROGATE_ALPHA = 1` and `OPTIMIZE_SURROGATE_BETA = 0` keeps the GPSAF entry point available while disabling surrogate calls.
- Variable count and objective count are deliberately absent from config and resolved through `job_template.api`.
- `JOBS_DIR` is the submit-side runtime staging location for prepared job folders. Worker-side scratch placement is an HTCondor `EXECUTE` setting, not a `JOBS_DIR` setting.
- When requiring RAM-disk workers, `HTCONDOR_REQUIREMENTS` can match the worker-advertised `YADOF_RAMDISK` attribute written by the pool setup tools.
- `HTCONDOR_PYTHON_EXE` defaults to `python`, letting each worker resolve Python from its own PATH. If an explicit path is used, it must be valid on every worker that can match the job.
- `EVALUATION_TIMEOUT_SEC` is the generation-level wait budget for distributed evaluation, not just a single HFSS solve timeout. Large populations submitted in waves need a value large enough for the full generation to drain.
- `HTCONDOR_REQUEST_MEMORY` is a scheduler reservation. It should be high enough for AEDT startup and solve memory so the pool does not overpack workers.
- `EVALUATION_MODE` can be `local` or `distributed`; tests should still force local or monkeypatched behavior instead of requiring a real pool.
- `LOCAL_EVALUATION_MAX_WORKERS` defaults to 1 to preserve simulator safety; raising it enables local per-individual subprocess parallelism for workflows that can run concurrently.
- `SURROGATE_TORCH_DEVICE = "auto"` prefers CUDA, then XPU, then CPU; tests may force CPU and smaller INR dimensions for speed.
- `SURROGATE_RAWDATA_IMPORTANCE_FLOOR` and `SURROGATE_RAWDATA_IMPORTANCE_BOOST` are passed to task-owned rawData importance hooks; they do not remove full-field training coverage. `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` caps how many high-dimensional rawData query points are sampled per training step when fields are very large; scalar and 1D rawData slots are still always included, and prediction, reconstruction, checkpoints, and historical error audits still use the full query table.
- `OPTIMIZE_NSGA3_REF_DIR_METHOD` and `OPTIMIZE_NSGA3_PARTITIONS` tune NSGA-III reference directions without reintroducing an algorithm-selection switch.
- `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` reserves real-evaluation candidates that bypass surrogate selection so surrogate bias cannot fully starve a tradeoff branch.
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` is interpreted against completed surrogate training generations. The default `2` allows a model to trail real simulation by one or two generations, then forces a blocking catch-up before the next surrogate-assisted submission.

## Mutability Profile
- Users may tune `config.py` often during experiments.
- `config_all.py` should change when the framework gains or renames a cross-module setting.
- Avoid adding task-specific workflow logic or cost definitions here.
- When a new config value affects stored history interpretation, document the consequence in blueprint and architecture docs.
