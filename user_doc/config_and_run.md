# Configure, smoke, run, and inspect

## Configuration precedence

Effective values are loaded in this order:

1. validated package defaults;
2. uppercase core campaign settings in workspace `config.py`;
3. temporary API/CLI overrides for one invocation.

Unknown uppercase settings and invalid values fail before a batch starts. Loading
never rewrites config. Use `yadof check --workspace PATH` to see the selected mode
and validate paths.

Common core workspace settings include `EVALUATION_MODE`, `EVALUATION_TIMEOUT_SEC`,
`LOCAL_EVALUATION_MAX_WORKERS`, `FAST_EVALUATION_MAX_WORKERS`,
`FAST_EVALUATION_SCRATCH_DIR`, `OPTIMIZE_POPULATION_SIZE`,
`OPTIMIZE_SMOKE_TEST_ENABLED`, `OPTIMIZE_RANDOM_SEED`,
`OPTIMIZE_ARCHIVE_KEY_DECIMALS`, `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG`, and
HTCondor request/calibration/timeout settings. Search, GPSAF, and surrogate model
parameters are explicit keyword arguments in the `submit/optimization.py` program;
they are not core config settings and cannot be changed with a temporary config
override. Task
physics and problem shape stay in fixed `submit/` and evaluate-side
`job_template/` roots. Complete program control flow and component configuration
stay only in `submit/optimization.py`, never in config.

### One-time component setting migration

Old component-specific uppercase names are deliberately unsupported. Move each
value from `config.py` to the corresponding factory call in
`submit/optimization.py`:

| Removed config name | Factory keyword |
| --- | --- |
| `OPTIMIZE_NSGA3_REF_DIR_METHOD` | `pymoo_nsga3(reference_direction_method=...)` |
| `OPTIMIZE_NSGA3_PARTITIONS` | `pymoo_nsga3(reference_direction_partitions=...)` |
| `OPTIMIZE_REFILL_ATTEMPTS` | `pymoo_ga(refill_attempts=...)` / `pymoo_nsga3(refill_attempts=...)` |
| `OPTIMIZE_CROSSOVER_PROBABILITY` | both pymoo factories: `crossover_probability` |
| `OPTIMIZE_MUTATION_PROBABILITY` | both pymoo factories: `mutation_probability` |
| `OPTIMIZE_CROSSOVER_ETA` | both pymoo factories: `crossover_eta` |
| `OPTIMIZE_MUTATION_ETA` | both pymoo factories: `mutation_eta` |
| `OPTIMIZE_DIM_MUT_PER_INDIVIDUAL` | both pymoo factories: `mutated_dimensions_per_individual` |
| `OPTIMIZE_SURROGATE_ALPHA` | `gpsaf_settings(alpha=...)` |
| `OPTIMIZE_SURROGATE_BETA` | `gpsaf_settings(beta=...)` |
| `OPTIMIZE_SURROGATE_GAMMA` | `gpsaf_settings(gamma=...)` |
| `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` | `gpsaf_settings(exploration_fraction=...)` |
| `SURROGATE_CONSTANT_ATOL` | `conditional_inr(constant_atol=...)` |
| `SURROGATE_TARGET_SCALE_FLOOR` | `conditional_inr(target_scale_floor=...)` |
| `SURROGATE_TORCH_DEVICE` | selected surrogate factory: `device=...` |
| `SURROGATE_INR_EPOCHS` | `conditional_inr(epochs=...)` |
| `SURROGATE_INR_ENSEMBLE_SIZE` | `conditional_inr(ensemble_size=...)` |
| `SURROGATE_INR_BATCH_SIZE` | `conditional_inr(batch_size=...)` |
| `SURROGATE_INR_LR` | `conditional_inr(learning_rate=...)` |
| `SURROGATE_INR_WEIGHT_DECAY` | `conditional_inr(weight_decay=...)` |
| `SURROGATE_INR_LOSS_BETA` | `conditional_inr(loss_beta=...)` |
| `SURROGATE_MAX_NONFINITE_FRACTION` | `conditional_inr(max_nonfinite_fraction=...)` |
| `SURROGATE_INR_X_LATENT_DIM` | `conditional_inr(x_latent_dim=...)` |
| `SURROGATE_INR_FIELD_EMB_DIM` | `conditional_inr(field_embedding_dim=...)` |
| `SURROGATE_INR_COORD_FOURIER_FEATURES` | `conditional_inr(coordinate_fourier_features=...)` |
| `SURROGATE_INR_HIDDEN_DIM` | `conditional_inr(hidden_dim=...)` |
| `SURROGATE_INR_HIDDEN_LAYERS` | `conditional_inr(hidden_layers=...)` |
| `SURROGATE_INR_TRAIN_QUERY_CHUNK` | `conditional_inr(train_query_chunk=...)` |
| `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` | `conditional_inr(train_query_sample_count=...)` |
| `SURROGATE_INR_SAMPLE_BATCH_EVAL` | `conditional_inr(sample_batch_eval=...)` |
| `SURROGATE_INR_QUERY_BATCH_EVAL` | `conditional_inr(query_batch_eval=...)` |
| `SURROGATE_INR_BOOTSTRAP_MEMBERS` | `conditional_inr(bootstrap_members=...)` |
| `SURROGATE_INR_BOOTSTRAP_FRACTION` | `conditional_inr(bootstrap_fraction=...)` |

`OPTIMIZE_POPULATION_SIZE`, `OPTIMIZE_RANDOM_SEED`,
`OPTIMIZE_ARCHIVE_KEY_DECIMALS`, and
`OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` remain core campaign settings. The surrogate
viewer selects its own available device automatically; a component `device=` value
controls that component's training and checkpoint recovery.

An explicitly selected `posterior_assisted_selector()` component keeps its pool, draw,
chunk, qNEHVI batch/restart/support, and real-exploration controls in
`submit/optimization.py`; there are no matching global config selectors. During a
fail-closed generation its compact metadata names the typed blocker and fallback
reason. During a legally enabled generation it records only bounded support,
projection, applicability, acquisition, timing, and selection diagnostics—never
predicted rawData or predicted costs as durable history.

Surrogate training uses only recorded real rawData rows. By default every independently
initialized ensemble member sees every retained real row; this preserves all measured
design support because ensemble spread is diagnostic and does not steer GPSAF.
`conditional_inr(bootstrap_members=True)` remains an explicit opt-in for seeded
bootstrap rows drawn only from that same evidence. It does not synthesize mixup targets
and does not accept task-owned rawData importance or relative-loss settings.
The `conditional_inr(train_query_sample_count=...)` argument bounds queries per
step; when a field is
larger than that budget, sampling is seeded, without replacement, and balanced across
modeled fields. Every active field has equal macro loss importance regardless of its
number of scalar positions. If the configured epoch/batch schedule would end before a
budget-smaller-than-field-count rotation gives every field the same number of
appearances, yadof extends that member's effective epoch count just enough to complete
one full rotation cycle and records both configured and effective counts.

For each modeled rawData query position, conditional INR centers recorded values at
their mean and scales them by their recorded standard deviation, with
`conditional_inr(target_scale_floor=...)` protecting near-constant positions.
Normalized design
variables are centered from `[0, 1]` to `[-1, 1]` inside the network. The decoder is
linear in this standard-score space, so it can predict beyond the minimum and maximum
already observed instead of saturating at a historical min/max envelope. Predicted
standard scores are always inverse-scaled back to rawData before current task cost is
calculated.

Advanced history-recorder settings are
`HISTORY_SEGMENT_MAX_CANDIDATES` (default 16),
`HISTORY_SEGMENT_TARGET_BYTES` (16 MiB),
`HISTORY_MAX_CANDIDATE_BYTES` (64 MiB),
`HISTORY_UNPUBLISHED_MAX_CANDIDATES` (default 32),
`HISTORY_UNPUBLISHED_MAX_BYTES` (512 MiB),
and `HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES` (3 attempts for the same pending
segment). Count and byte budgets are independent backpressure limits, not loss
allowances. When either unpublished budget is full, evaluation finalization waits
for the writer to publish enough evidence. Every evaluation/generation boundary
waits until all admitted evidence is durably published. Candidate/group receipts
remain pending after admission and become committed only after atomic segment
publication. Current-cost interpretation starts after that commit. Committed
rawData kept hot for not-yet-interpreted rows is bounded by the same explicit
count/byte limits; excess payload is reloaded from its immutable segment. A record
above the explicit
single-candidate safety limit or a writer that exhausts its retry count stops the
campaign before a later evaluation can begin. Recorder settings are frozen when a
campaign starts even though task-semantic configuration remains hot-reloadable at
generation boundaries.

## Local concurrency and resource calibration

`LOCAL_EVALUATION_MAX_WORKERS` is the user-directed concurrency cap and defaults
to 8. With enough candidates in the current population, yadof uses this value
without lowering it from detected CPU, memory, or disk capacity. Population size
remains the natural bound on simultaneously useful work.

With the default `LOCAL_RESOURCE_AUTODETECT_ENABLED = True`, yadof still observes
physical CPU capacity, available memory, and free disk against calibrated
per-workflow estimates. These values are advisory diagnostics only; they never
rewrite the configured worker cap.

`LOCAL_RESOURCE_SYSTEM_RESERVE_FRACTION` defaults to `0.15`, reserving 15% of
available memory and disk for the operating system and other work. The one-individual
smoke contract is unchanged.

Local execution samples the workflow process and recursive simulator children with
psutil. It records backend-neutral CPU, peak-memory, and disk fields alongside local
diagnostics. HTCondor collection writes the same neutral fields. Both backends call
one calibration implementation: generation zero uses compatible smoke evidence,
later generations use the preceding generation from the same optimizer run, and the
configured upper tail is trimmed before estimates are selected.

When no evidence exists, `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, and
`HTCONDOR_REQUEST_DISK` act as the shared per-job bootstrap hints. This preserves
existing workspace resource declarations across local and distributed execution.
`HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER` and
`HTCONDOR_RESOURCE_TRIM_TOP_FRACTION` also apply to the shared calibration.

`--progress` prints the effective local worker count, configured cap, advisory
CPU/memory/disk capacities, calibration source, and sample count. A temporary
`local_max_workers` API override changes the cap and is trusted in the same way.
Disabling `LOCAL_RESOURCE_AUTODETECT_ENABLED` suppresses adaptive observation and
calibration; it does not change worker-count authority.

## Fast concurrency, timeout, and scratch

`EVALUATION_MODE = "fast"` selects reusable process-isolated workers on the current
machine. `FAST_EVALUATION_MAX_WORKERS` defaults to 8 and is used without a host-
resource clamp when enough candidates are available. With
`FAST_RESOURCE_AUTODETECT_ENABLED = True`, yadof observes host CPU, available
memory, and free scratch disk divided by:

- `FAST_EVALUATION_CPUS_PER_WORKER` (default 1);
- `FAST_EVALUATION_MEMORY_MIB_PER_WORKER` (default 512);
- `FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER` (default 1024).

`FAST_RESOURCE_SYSTEM_RESERVE_FRACTION` defaults to `0.15`. These values produce
advisory diagnostics; they do not reduce `FAST_EVALUATION_MAX_WORKERS`. The
declarations are independent of HTCondor requests.
`EVALUATION_TIMEOUT_SEC` is the hard candidate timeout; timeout/crash kills the
worker tree and the next queued individual uses a replacement worker. A smoke still
disables the timeout and caps fast at one worker.

`FAST_EVALUATION_SCRATCH_DIR` defaults to `.yadof/fast_scratch`. It may be absolute
or workspace-relative but must not overlap `submit`, `job_template`, `jobs`,
`recorded_data`, checkpoints, logs, or tool output. Candidate subdirectories are temporary and normally leave the root
empty. A cleanup failure is persisted as `scratch_cleanup_error`; inspect it rather
than silently deleting evidence elsewhere. Fast subprocess environment overrides
are applied only inside a worker evaluation and restored before worker reuse.

## Execution authority and cost-based agent judgment

A user may delegate routine execution decisions to the AI agent. Before starting a
real smoke test or optimization, classify the concrete run rather than treating all
simulators alike. Inspect the selected workspace and mode, expected time per
evaluation, population and generation counts, concurrency, timeout behavior,
license or paid-service use, shared-machine or cluster impact, filesystem effects,
and whether the command can finish without interactive input. An explicit user
instruction may always narrow or broaden this default authority for the task.

The agent may proceed without another confirmation when the execution is understood
and bounded, expected to consume modest local time and resources, and has no
material external side effect beyond the selected workspace. Typical examples are:

- one smoke evaluation expected to finish in seconds or minutes on a known working
  local simulator;
- a deliberately bounded optimization using `test_com`, ngspice, or a simple
  Project Chrono model whose estimated evaluation count and total runtime are
  modest;
- focused integration checks whose simulator, license, output paths, and cleanup
  behavior have already been inspected.

Use explicit `--generations` and appropriate population/concurrency settings for an
agent-initiated optimization; do not silently rely on the 50-generation CLI default
when that would make the cost estimate unclear. A standalone smoke has no task
timeout, so a single midpoint evaluation is not automatically safe when the
workflow may hang.

Obtain explicit user authorization before starting an optimization or other run
that is expected to last many hours or days, has unknown or effectively unbounded
cost, consumes a scarce/shared license or cluster materially, incurs paid external
usage, changes external systems, or otherwise exceeds routine workspace-local work.
An HFSS smoke that is understood to take only a few minutes may normally be run by
the agent after `check`; a full HFSS optimization commonly takes days and therefore
requires an explicit user request. Project-specific evidence overrides these
examples: a complex ngspice or Project Chrono task can still require confirmation,
and an unusually small known-safe task may be treated proportionally.

When the user explicitly requests a long optimization, start it as a detached
operating-system process so the agent task does not own its lifetime. On Windows, a
separate hidden PowerShell process is an appropriate launcher. Redirect stdout and
stderr to workspace-owned log files, preserve the one-campaign-per-workspace rule,
and report the exact command, process ID when available, and log paths. After the
launcher succeeds, disconnect and finish the agent task: do not poll, wait for, or
periodically monitor the long run unless the user later asks for monitoring.

## Standalone smoke

```powershell
yadof smoke-test --workspace PATH --mode local
yadof smoke-test --workspace PATH --mode fast --real-task
yadof smoke-test --workspace PATH --mode distributed --real-task
```

A smoke evaluates exactly one midpoint individual with no generation index, no
per-job execution limit, and no submit-side whole-generation deadline. It succeeds
only if at least one finite objective is returned. Before it blocks on the real
workflow, the CLI immediately prints the selected workspace, evaluation mode, jobs
directory, and no-timeout warning. It then prints the returned costs on success or
an actionable error with the jobs directory on failure. Its durable evidence remains
available for diagnostics, views, and compatible resource calibration, but the
unindexed midpoint row is not optimizer history and cannot warm-start generation
zero. A new campaign therefore keeps its global random initialization unless
generation-scoped optimization evidence already exists.

For fast, the same feedback says that there is no durable job directory and prints
the ephemeral scratch root instead. Fast failure diagnostics are durable recorded
history metadata rather than job-local stdout/stderr files.

## Start or resume

```powershell
yadof run --workspace PATH
yadof run --workspace PATH --generations 5
yadof run --workspace PATH --start-generation 5 --generations 5
```

When `--generations` is omitted, the CLI runs 50 generations. Supplying
`--generations N` overrides that invocation. The Python `run_generations()` API
continues to require an explicit generation count.

Progress is enabled by default for `fast`, `local`, and `distributed` runs. Each
generation immediately displays a population progress bar and the numeric counts
of successful individuals, errors, and remaining individuals; it updates whenever
an individual reaches a terminal outcome. Backend scheduling, timeout, and retry
details remain visible alongside it. Fast worker-plan details are retained in
evaluation diagnostics instead of being printed once per generation. Use
`--no-progress` for a quiet invocation, or `--progress` to explicitly retain the
default. Progress settings are temporary and the caller environment is restored
afterward.

The pre-run real-task smoke default comes from
`OPTIMIZE_SMOKE_TEST_ENABLED`. `--smoke-test` and `--no-smoke-test` are opposite,
explicit overrides and take precedence. `--mode`, `--population-size`, and
`--random-seed` are also temporary.

When smoke is skipped, configured memory/disk and job-timeout baselines act as the
synthetic generation-zero calibration. Distributed normal jobs receive a scheduler
`allowed_execute_duration` and the submit side independently watches each active
execution from local Condor event timestamps. At the limit, yadof records timeout,
stops waiting, and attempts bounded `condor_rm` cleanup without requiring it to
succeed. The whole-generation deadline remains separate. Memory/disk holds may be
freshly resubmitted by yadof with bounded, independent doubling. yadof diagnoses
HTCondor but never installs or repairs it.

### Correct the task during a campaign

Task mutability is intentional. At a generation boundary, the user may change:

- `submit/calc_cost.py`, including objective names, meanings, and thresholds,
  while preserving the objective count;
- `job_template/parameters_constraints.py`, including ranges and levels, while
  preserving parameter names, order, and count;
- `config.py`;
- `job_template/workflow.py`, `evaluation.py`, adapters, and task helpers.

An optimization program and its declared helpers are different: their
bytes are frozen once for the complete `yadof run` command. To load a program edit,
let the current command stop at a complete generation, then start a new command at
the exact next generation. The removed 0.4.x factory path is not reloaded or
accepted by 0.5.0.

The corrected task is allowed to define a different optimization problem. Yadof
does not evaluate “scientific equivalence” between the old and new versions. It
trusts the user to decide whether earlier evidence remains useful. Current task
code attempts to reinterpret stored raw variables/rawData; a record is omitted only
when it cannot actually be normalized, loaded, or converted to the current
objective tuple. A source hash may identify that code changed, but it is not a
scientific rejection rule.

The current in-campaign correction contract assumes stable parameter identity,
parameter count, and objective count. Adding, removing, reordering, or renaming
parameters, or changing objective width, requires optimizer-state migration rules
that are not yet supported by this workflow. Use a new workspace/campaign for such
a structural change until that separate feature is implemented.

Use a generation boundary as the coherence point. Yadof takes one immutable task
snapshot of both complete source roots before the first candidate in each
generation. An edit made while that
generation runs cannot affect any of its candidates and is picked up at the next
boundary. You may still split commands when you want an explicit manual inspection
point:

```powershell
yadof run --workspace PATH --start-generation 0 --generations 10
# Edit the workspace task, then:
yadof check --workspace PATH
yadof run --workspace PATH --start-generation 10 --generations 10
```

The run/resume APIs load current configuration and non-program task definitions
once per subsequent generation. A complete task snapshot identity plus separate
interpretation/evaluation/optimization fingerprints is attached to every result.
The strategy signature and source fingerprint are separate: a comment-only edit
need not invalidate compatible state, while a changed backend, algorithm,
controlled parameter, parameter/objective shape, or surrogate policy activates an
isolated namespace. Fingerprints
provide provenance and cache invalidation; they never decide scientific
compatibility or reject a record by themselves.

Before continuing, the user should decide:

- Keep history when old raw variables and rawData are still meaningful under the
  correction.
- Run `yadof history clear --workspace PATH --yes` only when no old evidence should
  influence the corrected problem.
- Use a new workspace when both versions should remain independently reproducible
  or run concurrently.

This is a scientific/user decision rather than a framework inference. Run only one
active optimization campaign per workspace. Separate concurrent campaigns into
different workspaces.

Changing `submit/optimization.py` does not by itself require clearing real evidence.
Source-only edits keep the semantic identity but produce a
new source fingerprint on the next command. An identity change activates a new
strategy namespace and does not reuse the previous program-completion pointer.
For a compatible identity, the new command must use
`--start-generation` equal to the last completed generation plus one. Program
boundaries wait for pending component work, release memory state, retain namespaced
artifacts, and activate a changed semantic identity at the next command boundary.
A non-surrogate program produces no surrogate
state; the viewer reports that no compatible active checkpoints exist.

The Windows distributed submit contract runs `workflow.py` directly with
`transfer_executable=True`, `load_profile=True`, and `run_as_owner=False`. Input
transfer contains the task/job files and `worker_misc.py`, never a yadof runtime
package. Output transfer returns `rawData.zip` plus `individual_metadata.json` and
does not return `rawData/`. Missing, nested, or malformed zip contents become
per-individual diagnostics.

## History and tools

```powershell
yadof view cost --workspace PATH [--status completed] [-o NAME.png] [--summary-only]
yadof view time --workspace PATH [--status all] [-o NAME.png] [--summary-only]
yadof view all --workspace PATH [--summary-only]
yadof view surrogate [--workspace PATH]
yadof view surrogate summary --workspace PATH [--format text|json]
yadof view surrogate audit --workspace PATH [--sample-percent 10] `
  [--random-seed N] [--metric relative|absolute|both] `
  [--quantity all-costs|cost:NAME|all-rawdata|rawdata:NAME] `
  [--format text|json] [--progress]
yadof view surrogate inspect --workspace PATH `
  [--checkpoint-generation N|latest] `
  (--job-name NAME | --real-generation N --population-index N) `
  --rawdata NAME [--plot-dimension NAME] [--plot-dimension NAME] `
  [--fixed-coordinate NAME=VALUE] [--format text|json] `
  [--output NEW_OR_EMPTY_DIRECTORY]
yadof history clear --workspace PATH --yes
yadof task adapters
yadof task copy-adapter test_com.py --workspace PATH
```

The cost view shows objective history. Its `avg. cost` series is the arithmetic
mean of every objective and shares the left cost axis, preserving the same plotted
height that the former objective-count-scaled combined-cost axis produced. The
right axis shows hypervolume: the shaded band is bounded above by the cumulative
hypervolume of all recorded generations and below by the current generation's
hypervolume, using the fixed normalized-cost reference point `(1, ..., 1)`. Thin,
translucent upper and lower polylines connect the values at each generation plotting
position while the interval remains shaded. Objective
names appear in the Pareto-table header, without a separate redundant
`objectives:` summary line. At the start of one `view cost` command, yadof freezes
the finalized history-segment list and the current parameter/cost definitions. It
then opens each frozen segment once to decode and validate rawData before
recalculating cost, so newly published records or task edits are picked up by the
next command rather than mixed into the active result. The CLI displays cost-history calculation progress on
stderr while leaving the summary on stdout; an interactive progress frame is
overwritten in place and each stage leaves only its final line. The HV legend is
abbreviated as `HV (all & current gen.)`, and dense generation numbers alternate
between two heights. The time view combines elapsed time, failure
rate, execute-machine colors, and error occurrences. Its elapsed-time axis
automatically uses minutes for minute-scale completed evaluations, seconds below a
minute, and milliseconds below a second; its upper limit is proportional to the
completed durations instead of being fixed at one minute. Average-time curves and each
machine's average use completed evaluations only; failed evaluations are excluded
from time averages and remain visible through the failure/error encodings. Each
cost-history row that cannot be plotted is isolated instead of aborting the whole
cost view. This includes malformed, non-numeric, non-finite, empty, overflowed, or
minority objective-width rows. The summary reports the ignored issues, and the PNG
uses every remaining valid row while preserving its original evaluation index.
Optional individual/optimization annotations are omitted when their metadata cannot
be read, and unavailable task objective names fall back to deterministic generic
labels. An unreadable core history or a history with no plottable row remains an
actionable error. Each
error type occupies a left-labeled horizontal band near the top of the plot, with
the label centered on the line. Each machine legend entry includes that machine's
average completed elapsed time; an error marker's fill identifies the execute
machine and its outer ring identifies the error type. The execute machine comes from
`individual_metadata.json` written by package worker support in the execute-side
workflow process whenever that file returns. If timeout prevents its return, yadof
may fall back to the final relevant execution segment in the job-local Condor user
log; this source-labeled value never overrides worker identity. A job that timed out
without ever executing remains `unknown`. Historical records can derive this value
in memory from their stored log tail, without changing recorded evidence.
Failure-rate timing prefers the workflow or scheduler-observed execution start from
either the individual row or its job metadata; the later evidence-recording
timestamp is only a last resort, so segment publication does not artificially
cluster failures at a boundary.

Individual view commands print a summary and create
`cost_YYYYMMDD_HHMMSS.png` or `time_YYYYMMDD_HHMMSS.png` by default.
`-o/--output` overrides the individual view's name or path; relative plot names are
written below `.yadof/tool_output/`. `view all` runs cost and time together, prints
both summaries, and creates both timestamped images. Use `--summary-only` to print
without creating PNGs. Destructive history clear requires interactive confirmation
or `--yes`, validates its exact workspace targets, refuses while the campaign lock
is held, clears only generated segment/event history, the active optimization-state
pointer, surrogate checkpoints, and jobs in that workspace, and recreates the jobs
directory. Other entries below `recorded_data/`
remain untouched.

`view surrogate` is a separate, explicitly launched read-only tool. With no mode,
or with the explicit `gui` mode, it opens the selected workspace (or lets the user
choose one), explores saved surrogate checkpoint predictions and recorded real
evidence, and can calculate an in-memory cross-generation error audit. It accepts
committed checkpoints whose parameter ranges/levels still match the current task;
older INR hyperparameter configurations remain viewable because the artifact's own
persisted train config is used. For each
rawData output it lists every dimension: select zero, one, or two as plot axes and
enter coordinates for the remaining dimensions. Each fixed dimension has both a
checkpoint-grid dropdown and a finite-value entry. Stored values preserve the
checkpoint's original full-grid prediction path. Conditional-INR checkpoints query
their decoder at off-grid values and interpolate the stored per-coordinate target
scaler; coordinate-enabled hierarchical-CAE checkpoints query their task-neutral
all-axis coordinate readout and reject values outside the stored domain. A workspace
view selects one compatible active component namespace and never mixes methods.
PCA/SVD checkpoints appear as one deterministic member: prediction, stored-grid
slice, and audit are supported, while the viewer does not invent ensemble spread or
an off-grid decoder for that model.
The interactive plot then shows a scalar value, a curve, or a
filled two-dimensional color contour without contour lines. Recorded truth is
omitted for off-grid rawData positions because no such evidence exists. Continuous
task parameters remain independently queryable between recorded samples.

Hierarchical coordinate checkpoints are explicitly experimental and
performance-not-accepted. Their full-grid decoder remains authoritative for the
objective bars, audit, optimizer, and posterior; the coordinate path is a read-only
viewer/off-grid capability and does not imply that Gate 0 v5 passed.

The three terminal modes are intended for people and AI agents that need analysis
without a window:

- `summary` does not load a model. It prints checkpoint generations/member counts,
  training policy and semantic signature, completed-result counts by optimization generation, parameter ranges,
  objective names, and rawData dimension spans. `--format json` emits a
  schema-versioned machine-readable object.
- `audit` performs the same checkpoint inference and per-generation sampling as
  the GUI audit. It prints a matrix whose rows are optimization generations and
  columns are checkpoint generations. `--quantity` selects all costs, one named
  cost, all rawData, or one named rawData output; `--metric both` returns both
  aggregate matrices from the single inference pass. JSON represents missing
  finite aggregates as `null`. `--progress` writes status to stderr so stdout
  remains clean for text or JSON capture.
- `inspect` deterministically reproduces one checkpoint/real-result/rawData slice.
  Select the real result by exact `--job-name` or by the complete
  `--real-generation` plus `--population-index` pair. Checkpoint `latest` is the
  default. Plot dimensions and fixed coordinates use exact rawData dimension
  names; omitted plot dimensions select `Freq` when present or the first axis,
  while omitted fixed values select the stored coordinate nearest zero. The
  resolved defaults, stored-grid/off-grid status, parameter values, objective
  comparison, ensemble range, finite error statistics, and any warning are all
  recorded in the result. Off-grid queries have no recorded truth, so `truth` and
  `error_summary` are `null`.

`inspect --format json` inlines coordinates and selected prediction/truth/ensemble
arrays only when the selected plot has at most 4096 scalar values. Larger plots
retain shapes and finite statistics, set `values_omitted=true`, and direct the
caller to explicit evidence export. Non-finite values are always JSON `null`,
never `NaN` or `Infinity`.

Without `--output`, `inspect` creates no PNG, cache, manifest, or other file. With
an explicit new or empty directory it writes `manifest.json`, `data.npz`, and a
pure Matplotlib/Agg `plot.png`; one-dimensional selections also receive
`curve.csv`. The manifest records relative artifact paths, sizes, and SHA-256
digests and is published only after every other artifact succeeds. Existing
non-empty output directories and existing artifact names are never overwritten.

All terminal modes default to the current directory when `--workspace` is omitted.
`summary` and `audit` always write nothing; `inspect` writes only its explicitly
requested output directory. None changes configuration, history, recorded data,
or checkpoints. For a parsed command using `--format json`, a runtime failure
leaves stdout empty and writes one schema-versioned `surrogate_tool_error` object
to stderr with stable `code`, `message`, `details`, and `hints` fields. The
surrogate tool never joins `view all`, starts a workflow, or changes training and
checkpoint artifacts. Install the `viewer` extra before using any of its modes.

## Python APIs

Every stateful public call takes a workspace:

```python
from yadof.evaluate_manager import (
    evaluate_population,
    prepare_evaluation,
    run_smoke_test,
    start_evaluation,
)
from yadof.optimize import run_generations

run_smoke_test("D:/work/study-a", mode="local")
run_generations("D:/work/study-a", 3, start_generation=0)

batch = prepare_evaluation("D:/work/study-a", ((0.25,),), mode="local")
with start_evaluation(batch) as handle:
    finalized = handle.wait()
print(finalized.costs)
```

The explicit handle is useful only when caller code has independent bounded work or
needs cancellation. Preparing a batch performs no evaluation and opens no runtime
resource. `evaluate_population()` remains the concise synchronous form and uses the
same handle internally.
