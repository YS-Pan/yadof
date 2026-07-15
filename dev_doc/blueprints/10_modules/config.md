# Module blueprint: config

## Intent
- Provide a layered configuration package for generic cross-module settings and
  explicitly software-specific extensions.
- Keep `project/config/key.py` small enough for routine campaign edits while
  preserving a full grouped reference in `project/config/all.py`.
- Keep problem shape and objective schema out of config; those belong to `job_template.api`.

## Historical Lineage
- Optimizer and evaluation launch settings descend from fanyufei-style `optConfig` concepts.
- Surrogate and generation-plan controls descend from shorten-style experiment configuration.
- Current config keeps task shape and objective semantics out of global settings; those belong to `job_template.api`.

## Functionalities
- `project/config/key.py` defines only generic key settings users are likely to edit for a new optimization campaign. It contains constants only.
- `project/config/all.py` imports `key.py`, groups all generic defaults by area, and uses matching names from `key.py` as overrides.
- `project/config/specific/` owns settings tied to a simulator or vendor. The current `hfss.py` owns HFSS/PyAEDT runtime defaults and its HTCondor environment contribution.
- `project/config/specific/__init__.py` is the extension boundary through which active specific modules contribute settings such as HTCondor environment entries without embedding simulator names in generic config code.
- Generic config consumers that need a refresh reload extensions exposed through
  `config.specific` before reloading `all.py`; they must not import a concrete
  `specific/<software>.py` module.
- Defines derived root paths such as `PROJECT_ROOT`, `JOBS_DIR`, and `SURROGATE_CHECKPOINT_DIR` in the full config.
- Selects `EVALUATION_MODE` and timeout behavior.
- Defines local evaluation worker count for parallel-safe local workflows.
- Defines HTCondor command/resource/submit defaults for distributed evaluation,
  including automatic memory/disk calibration parameters.
- Keeps workflow-side simulator defaults out of generic `key.py` and `all.py`.
- Defines optimizer population, random seed, NSGA-III reference-direction controls, pymoo operator parameters, duplicate-key rounding, and refill behavior.
- Defines surrogate model, torch device selection, conditional-INR training, target scaling, task-owned rawData importance weighting, stochastic training query limits, and error hyperparameters.
- Defines GPSAF surrogate assistance controls: `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, `OPTIMIZE_SURROGATE_GAMMA`, `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION`, and `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG`.

## I/O Format
- Generic runtime modules import `project.config.all`; software-specific workflow code imports its matching module under `project.config.specific`.
- `key.py` and `all.py` must remain software-agnostic. `key.py` contains constants only; `all.py` may contain generic composition helpers but not task logic or simulator-named settings.
- Paths are `Path` objects rooted in `project/` when they are derived in `all.py`, whose file now lives one directory below the project root.
- Numeric controls should be simple Python scalars.
- Local and HTCondor controls are simple strings, numbers, and booleans such as `EVALUATION_TIMEOUT_SEC`, `LOCAL_EVALUATION_MAX_WORKERS`, `HTCONDOR_SUBMIT_EXE`, `HTCONDOR_HISTORY_EXE`, `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, `HTCONDOR_REQUEST_DISK`, `HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER`, `HTCONDOR_RESOURCE_TRIM_TOP_FRACTION`, `HTCONDOR_RESOURCE_RETRY_DOUBLINGS`, `HTCONDOR_REQUEST_DISK_MULTIPLIER`, `HTCONDOR_ENVIRONMENT`, `HTCONDOR_LOAD_PROFILE`, `HTCONDOR_RUN_AS_OWNER`, and `HTCONDOR_REQUIREMENTS`.

## Non-Obvious Techniques
- `project/config/key.py` is intentionally short. Its current surface includes evaluation mode/timeout, generic HTCondor resources, and population size.
- `project/config/all.py` is the generic discovery layer. Adding a new cross-module setting usually means adding it there first, then deciding whether it belongs in `key.py` or a `specific/<software>.py` module.
- `evaluate_manager` copies the complete `project/config/` package into every prepared job folder, excluding caches, so submitted jobs retain generic and active software-specific context.
- The active HFSS `workflow.py` reads job-local `config.specific.hfss`, then allows the corresponding HTCondor environment variables to override runtime values.
- The default HTCondor environment follows quoted, whitespace-separated HTCondor syntax. Do not use semicolon-separated entries in the quoted environment string.
- `HTCONDOR_REQUEST_CPUS` stays a manual scheduler request. The current HFSS
  extension derives `HFSS_JOB_CPUCORE` from it through
  `HFSS_CPUCORE_MULTIPLIER` (default `2`), so solver cores may intentionally exceed
  the scheduler request. That is a throughput trade-off, not a reservation for
  extra Condor CPUs.
- Setting `OPTIMIZE_SURROGATE_ALPHA = 1` and `OPTIMIZE_SURROGATE_BETA = 0` keeps the GPSAF entry point available while disabling surrogate calls.
- Variable count and objective count are deliberately absent from config and resolved through `job_template.api`.
- `JOBS_DIR` is the submit-side runtime staging location for prepared job folders. Worker-side scratch placement is an HTCondor `EXECUTE` setting, not a `JOBS_DIR` setting.
- When requiring RAM-disk workers, `HTCONDOR_REQUIREMENTS` can match the worker-advertised `YADOF_RAMDISK` attribute written by the pool setup tools.
- The HTCondor submit executable is not a config setting. Distributed jobs use direct `workflow.py` submission with `transfer_executable = True`; Python interpreter access is a worker environment/file-association prerequisite, not a submit-file executable path.
- Config defaults must not encode machine-specific absolute install paths or require project-specific system environment variables. Use repository-relative derived paths, explicit user-provided settings, or environment variables that the relevant external installer already creates.
- `EVALUATION_TIMEOUT_SEC` is the generation-level wait budget for distributed evaluation, not just a single HFSS solve timeout. Large populations submitted in waves need a value large enough for the full generation to drain.
- `HTCONDOR_REQUEST_MEMORY` is a scheduler reservation. It should be high enough for AEDT startup and solve memory so the pool does not overpack workers.
- `HTCONDOR_REQUEST_MEMORY` and `HTCONDOR_REQUEST_DISK` are bootstrap values for
  `evaluate_manager.resource_requests`. A distributed smoke test supplies the
  first calibration; generation zero applies
  `HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER`, then each following generation uses
  the prior generation's highest remaining memory/disk measurement after removing
  `HTCONDOR_RESOURCE_TRIM_TOP_FRACTION` from the top. Disk additionally applies
  `HTCONDOR_REQUEST_DISK_MULTIPLIER` after calibration.
- `HTCONDOR_RESOURCE_RETRY_DOUBLINGS` limits the finite `2x`, `4x`, ... retry
  ladder emitted for both memory and disk. The bounded ladder keeps an accidental
  unlimited request from entering a submit file while allowing unusual jobs to
  retry after a resource eviction.
- `EVALUATION_MODE` can be `local` or `distributed`; tests should still force local or monkeypatched behavior instead of requiring a real pool.
- `LOCAL_EVALUATION_MAX_WORKERS` defaults to 1 to preserve simulator safety; raising it enables local per-individual subprocess parallelism for workflows that can run concurrently.
- `SURROGATE_TORCH_DEVICE = "auto"` prefers CUDA, then XPU, then CPU; tests may force CPU and smaller INR dimensions for speed.
- `SURROGATE_RAWDATA_IMPORTANCE_FLOOR` and `SURROGATE_RAWDATA_IMPORTANCE_BOOST` are passed to task-owned rawData importance hooks; they do not remove full-field training coverage. `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` caps how many high-dimensional rawData query points are sampled per training step when fields are very large; scalar and 1D rawData slots are still always included, and prediction, reconstruction, checkpoints, and historical error audits still use the full query table.
- `OPTIMIZE_NSGA3_REF_DIR_METHOD` and `OPTIMIZE_NSGA3_PARTITIONS` tune NSGA-III reference directions without reintroducing an algorithm-selection switch.
- `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` reserves real-evaluation candidates that bypass surrogate selection so surrogate bias cannot fully starve a tradeoff branch.
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` is interpreted against completed surrogate training generations. The default `2` allows a model to trail real simulation by one or two generations, then forces a blocking catch-up before the next surrogate-assisted submission.

## Mutability Profile
- Users may tune `config/key.py` often during experiments and the active file under `config/specific/` when its simulator settings change.
- `config/all.py` should change when the framework gains or renames a generic cross-module setting.
- Add a new file under `config/specific/` for a new simulator's settings; do not add those names to `key.py` or `all.py`.
- Avoid adding task-specific workflow logic or cost definitions anywhere in config.
- When a new config value affects stored history interpretation, document the consequence in blueprint and architecture docs.
