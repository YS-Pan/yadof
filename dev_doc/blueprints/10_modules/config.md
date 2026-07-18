# Module blueprint: config

## Intent
- Provide a layered configuration package for generic cross-module settings and
  explicitly software-specific extensions.
- Provide the installed package-era configuration contract as immutable package
  defaults merged with one selected workspace's short `config.py` and optional
  temporary overrides.
- Keep `project/config/key.py` small enough for routine campaign edits while
  preserving a full grouped reference in `project/config/all.py`.
- Keep problem shape and objective schema out of config; those belong to `job_template.api`.

## Historical Lineage
- Optimizer and evaluation launch settings descend from fanyufei-style `optConfig` concepts.
- Surrogate and generation-plan controls descend from shorten-style experiment configuration.
- Current config keeps task shape and objective semantics out of global settings; those belong to `job_template.api`.

## Functionalities
- `yadof.workspace.WorkspaceContext` resolves an explicit root, fixed root
  `config.py`, task inputs, jobs, recorded data, surrogate checkpoints, logs, and
  tool output to absolute paths without creating them.
- `yadof.config.load_config` executes workspace `config.py` in a fresh namespace,
  validates uppercase names/types/modes/resources/task paths, merges precedence as
  package default < workspace config < temporary override, and reports each final
  value's source.
- `yadof init` creates a deliberately short config that selects local mode and a
  small smoke-oriented population while relying on package defaults for the full
  surface. `yadof check` loads the same effective config and diagnoses the selected
  backend without applying overrides or rewriting the file.
- `yadof.evaluate_manager` reloads the effective config for every population/smoke
  call. Packaged local jobs receive only mode, effective timeout, and local worker
  count with provenance; `run_smoke_test` temporarily forces local mode, one worker,
  and no timeout without rewriting workspace config.
- Relative configured paths resolve from the workspace root. Only an explicit
  absolute context/config/override value may place a path elsewhere. The loader
  never derives writable paths from installed package locations and never rewrites
  `config.py` for a temporary override.
- `project/config/key.py` defines only generic key settings users are likely to edit for a new optimization campaign. It contains constants only.
- `project/config/all.py` imports `key.py`, groups all generic defaults by area, and uses matching names from `key.py` as overrides.
- `project/config/specific/` owns settings tied to a simulator or vendor. The current `hfss.py` owns HFSS/PyAEDT runtime defaults and its HTCondor environment contribution.
- `project/config/specific/__init__.py` is the extension boundary through which active specific modules contribute settings such as HTCondor environment entries without embedding simulator names in generic config code.
- Generic config consumers that need a refresh reload extensions exposed through
  `config.specific` before reloading `all.py`; they must not import a concrete
  `specific/<software>.py` module.
- Defines derived root paths such as `PROJECT_ROOT`, `JOBS_DIR`, and `SURROGATE_CHECKPOINT_DIR` in the full config.
- Selects `EVALUATION_MODE`, the optional launch smoke test, the submit-side generation wait budget, and the HTCondor per-job timeout mode/baseline.
- Defines local evaluation worker count for parallel-safe local workflows.
- Defines HTCondor command/resource/submit defaults for distributed evaluation,
  including automatic memory/disk calibration and per-job time-limit parameters.
- Keeps workflow-side simulator defaults out of generic `key.py` and `all.py`.
- Defines optimizer population, random seed, NSGA-III reference-direction controls, pymoo operator parameters, duplicate-key rounding, and refill behavior.
- Defines surrogate model, torch device selection, conditional-INR training, target scaling, task-owned rawData importance weighting, stochastic training query limits, and error hyperparameters.
- Defines GPSAF surrogate assistance controls: `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, `OPTIMIZE_SURROGATE_GAMMA`, `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION`, and `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG`.

## I/O Format
- Package-era callers pass a workspace root or `WorkspaceContext` and receive a
  `LoadedConfig` with `.workspace`, mapping/attribute access to immutable final
  values, `.source_for(name)`, and `.describe()` output showing precedence.
- Package path settings are `JOB_TEMPLATE_DIR`, `JOBS_DIR`, `RECORDED_DATA_DIR`,
  `SURROGATE_CHECKPOINT_DIR`, `LOGS_DIR`, and `TOOL_OUTPUT_DIR`. Their effective
  values are absolute `Path` objects.
- Workspace config files define only recognized uppercase settings. Imports and
  private/lowercase helpers are not settings; unknown uppercase names are errors.
- Generic runtime modules import `project.config.all`; software-specific workflow code imports its matching module under `project.config.specific`.
- `key.py` and `all.py` must remain software-agnostic. `key.py` contains constants only; `all.py` may contain generic composition helpers but not task logic or simulator-named settings.
- Paths are `Path` objects rooted in `project/` when they are derived in `all.py`, whose file now lives one directory below the project root.
- Numeric controls should be simple Python scalars.
- Local and HTCondor controls are simple strings, numbers, and booleans such as `EVALUATION_TIMEOUT_SEC`, `OPTIMIZE_SMOKE_TEST_ENABLED`, `LOCAL_EVALUATION_MAX_WORKERS`, `HTCONDOR_SUBMIT_EXE`, `HTCONDOR_HISTORY_EXE`, `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, `HTCONDOR_REQUEST_DISK`, `HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER`, `HTCONDOR_RESOURCE_TRIM_TOP_FRACTION`, `YADOF_RESOURCE_RETRY_DOUBLINGS`, `HTCONDOR_REQUEST_DISK_MULTIPLIER`, `HTCONDOR_JOB_TIMEOUT_MODE`, `HTCONDOR_JOB_TIMEOUT_SEC`, `HTCONDOR_JOB_TIMEOUT_MULTIPLIER`, `HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION`, `HTCONDOR_ENVIRONMENT`, `HTCONDOR_LOAD_PROFILE`, `HTCONDOR_RUN_AS_OWNER`, and `HTCONDOR_REQUIREMENTS`.

## Non-Obvious Techniques
- A supplied `WorkspaceContext` may carry explicit path choices. Those choices
  override package path defaults, while an explicit value in its `config.py` and a
  temporary override retain the normal later precedence.
- Config source is compiled from current bytes in a fresh module object, so repeated
  calls see edits without mutating `sys.path` or caching a config module.
- Task path validation is split deliberately: `load_config` verifies the workspace
  root, task directory, and required task filenames before batch work;
  `yadof.job_template.validate_task` performs parameter/objective module validation
  without importing or running `workflow.py`.
- Init/check reuse this loader rather than duplicating config semantics. Init loads
  only staged generic content before publication; check reports load errors and then
  skips task/backend checks that require a valid config.
- `project/config/key.py` is intentionally short. Its current surface includes evaluation mode/generation timeout, the optional smoke switch, generic HTCondor resources, the auto/fixed per-job timeout baseline, and population size.
- `project/config/all.py` is the generic discovery layer. Adding a new cross-module setting usually means adding it there first, then deciding whether it belongs in `key.py` or a `specific/<software>.py` module.
- The transitional source evaluator still copies `project/config/`. The packaged
  local evaluator does not copy package config source; it writes a compact
  `yadof_worker_config.json` containing only effective worker-side local settings
  needed for diagnosis/execution.
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
- `HTCONDOR_JOB_TIMEOUT_SEC` is a separate one-individual baseline and defaults to one hour. `HTCONDOR_JOB_TIMEOUT_MODE = "auto"` is the default; its multiplier (`2.0`) and top trim (`0.10`) remain advanced settings in `all.py`. Smoke has no time limit. If smoke is disabled, the baseline is treated as its measured duration for generation-zero calibration.
- `HTCONDOR_REQUEST_MEMORY` is a scheduler reservation. It should be high enough for AEDT startup and solve memory so the pool does not overpack workers.
- `HTCONDOR_REQUEST_MEMORY` and `HTCONDOR_REQUEST_DISK` are bootstrap values for
  `evaluate_manager.resource_requests`. A distributed smoke test supplies the
  first calibration; generation zero applies
  `HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER`, then each following generation uses
  the prior generation's highest remaining memory/disk measurement after removing
  `HTCONDOR_RESOURCE_TRIM_TOP_FRACTION` from the top. Disk additionally applies
  `HTCONDOR_REQUEST_DISK_MULTIPLIER` after calibration.
- If smoke is disabled, automatic memory/disk calibration likewise treats the user-entered bootstrap requests as smoke measurements and applies `HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER` for generation zero.
- `YADOF_RESOURCE_RETRY_DOUBLINGS` defaults to `4` and limits fresh yadof
  resubmissions after standard memory or disk exhaustion. The counts are independent
  per resource, each retry doubles only the exhausted request, and `0` disables this
  retry behavior. No Condor-native retry ladder is emitted.
- `EVALUATION_MODE` can be `local` or `distributed`; tests should still force local or monkeypatched behavior instead of requiring a real pool.
- `LOCAL_EVALUATION_MAX_WORKERS` defaults to 1 to preserve simulator safety; raising it enables local per-individual subprocess parallelism for workflows that can run concurrently.
- `SURROGATE_TORCH_DEVICE = "auto"` prefers CUDA, then XPU, then CPU; tests may force CPU and smaller INR dimensions for speed.
- `SURROGATE_RAWDATA_IMPORTANCE_FLOOR` and `SURROGATE_RAWDATA_IMPORTANCE_BOOST` are passed to task-owned rawData importance hooks; they do not remove full-field training coverage. `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` caps how many high-dimensional rawData query points are sampled per training step when fields are very large; scalar and 1D rawData slots are still always included, and prediction, reconstruction, checkpoints, and historical error audits still use the full query table.
- `OPTIMIZE_NSGA3_REF_DIR_METHOD` and `OPTIMIZE_NSGA3_PARTITIONS` tune NSGA-III reference directions without reintroducing an algorithm-selection switch.
- `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` reserves real-evaluation candidates that bypass surrogate selection so surrogate bias cannot fully starve a tradeoff branch.
- `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` is interpreted against completed surrogate training generations. The default `2` allows a model to trail real simulation by one or two generations, then forces a blocking catch-up before the next surrogate-assisted submission.

## Mutability Profile
- `src/yadof/config.py` owns package defaults, validation, precedence, and the public
  immutable loaded-config contract. `src/yadof/workspace.py` owns path layout. Both
  are installed shared framework code.
- Package-era users edit only workspace `config.py`; temporary API/CLI overrides are
  intentionally non-persistent.
- Users may tune `config/key.py` often during experiments and the active file under `config/specific/` when its simulator settings change.
- `config/all.py` should change when the framework gains or renames a generic cross-module setting.
- Add a new file under `config/specific/` for a new simulator's settings; do not add those names to `key.py` or `all.py`.
- Avoid adding task-specific workflow logic or cost definitions anywhere in config.
- When a new config value affects stored history interpretation, document the consequence in blueprint and architecture docs.
