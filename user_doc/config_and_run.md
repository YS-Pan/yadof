# Configure, smoke, run, and inspect

## Configuration precedence

Effective values are loaded in this order:

1. validated package defaults;
2. uppercase settings in workspace `config.py`;
3. temporary API/CLI overrides for one invocation.

Unknown uppercase settings and invalid values fail before a batch starts. Loading
never rewrites config. Use `yadof check --workspace PATH` to see the selected mode
and validate paths.

Common workspace settings include `EVALUATION_MODE`, `EVALUATION_TIMEOUT_SEC`,
`LOCAL_EVALUATION_MAX_WORKERS`, `FAST_EVALUATION_MAX_WORKERS`,
`FAST_EVALUATION_SCRATCH_DIR`, `OPTIMIZE_POPULATION_SIZE`,
`OPTIMIZE_SMOKE_TEST_ENABLED`, HTCondor request/calibration/timeout settings, GPSAF
alpha/beta/gamma controls, and surrogate training controls. Task physics and problem
shape stay in `job_template/`.

## Local concurrency and resource calibration

`LOCAL_EVALUATION_MAX_WORKERS` is a safety cap, not always the number that will run.
Its package default is 8. With the default
`LOCAL_RESOURCE_AUTODETECT_ENABLED = True`, yadof plans every local batch from the
minimum of:

- the current population size and configured cap;
- physical CPU count divided by estimated CPU cores per workflow;
- available memory divided by estimated peak process-tree memory;
- free disk divided by estimated job-directory disk use.

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

`--progress` prints the effective local worker count, the configured/CPU/memory/disk
limits, calibration source, and sample count. A temporary `local_max_workers` API
override changes the cap; autodetection may still select a smaller safe count.
Disable `LOCAL_RESOURCE_AUTODETECT_ENABLED` only to use the cap directly.

## Fast concurrency, timeout, and scratch

`EVALUATION_MODE = "fast"` selects reusable process-isolated workers on the current
machine. `FAST_EVALUATION_MAX_WORKERS` defaults to 8. With
`FAST_RESOURCE_AUTODETECT_ENABLED = True`, the effective count is the minimum of
population/cap and host CPU, available memory, and free scratch disk divided by:

- `FAST_EVALUATION_CPUS_PER_WORKER` (default 1);
- `FAST_EVALUATION_MEMORY_MIB_PER_WORKER` (default 512);
- `FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER` (default 1024).

`FAST_RESOURCE_SYSTEM_RESERVE_FRACTION` defaults to `0.15`. These are explicit fast
task/simulator declarations and are independent of HTCondor requests.
`EVALUATION_TIMEOUT_SEC` is the hard candidate timeout; timeout/crash kills the
worker tree and the next queued individual uses a replacement worker. A smoke still
disables the timeout and caps fast at one worker.

`FAST_EVALUATION_SCRATCH_DIR` defaults to `.yadof/fast_scratch`. It may be absolute
or workspace-relative but must not overlap `job_template`, `jobs`, or
`recorded_data`. Candidate subdirectories are temporary and normally leave the root
empty. A cleanup failure is persisted as `scratch_cleanup_error`; inspect it rather
than silently deleting evidence elsewhere. Fast subprocess environment overrides
are applied only inside a worker evaluation and restored before worker reuse.

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
an actionable error with the jobs directory on failure.

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
an individual reaches a terminal outcome. Backend planning, scheduling, timeout,
and retry details remain visible alongside it. Use `--no-progress` for a quiet
invocation, or `--progress` to explicitly retain the default. Progress settings are
temporary and the caller environment is restored afterward.

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

Task mutability is intentional. Between generations, the user may change:

- `job_template/calc_cost.py`, including objective names, meanings, and thresholds,
  while preserving the objective count;
- `job_template/parameters_constraints.py`, including ranges and levels, while
  preserving parameter names, order, and count;
- `config.py`;
- `job_template/workflow.py`, `evaluation.py`, adapters, and task helpers.

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

Use a generation boundary as the coherence point. For a strictly controlled edit
with the current command surface, run a finite group of generations, let that
command return, edit and check the task, then resume:

```powershell
yadof run --workspace PATH --start-generation 0 --generations 10
# Edit the workspace task, then:
yadof check --workspace PATH
yadof run --workspace PATH --start-generation 10 --generations 10
```

The run/resume APIs load current configuration and task definitions for subsequent
generations. Do not edit files while candidates from a generation are being
prepared or executed when a coherent transition matters; already prepared or
running work may have captured the earlier source. Splitting the command at the
boundary avoids mixing definitions inside one generation.

Before continuing, the user should decide:

- Keep history when old raw variables and rawData are still meaningful under the
  correction.
- Run `yadof history clear --workspace PATH --yes` when no old evidence should
  influence the corrected problem.
- Use a new workspace when both versions should remain independently reproducible
  or run concurrently.

This is a scientific/user decision rather than a framework inference. Run only one
active optimization campaign per workspace. Separate concurrent campaigns into
different workspaces.

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
yadof history clear --workspace PATH --yes
yadof task adapters
yadof task copy-adapter test_com.py --workspace PATH
```

The cost view shows objective history. Its `avg. cost` series is the arithmetic
mean of every objective and shares the left cost axis, preserving the same plotted
height that the former objective-count-scaled combined-cost axis produced. The
right axis shows hypervolume: the shaded band is bounded above by the cumulative
hypervolume of all recorded generations and below by the current generation's
hypervolume, using the fixed normalized-cost reference point `(1, ..., 1)`. The
two boundaries are conveyed by the shade and are not drawn as lines. Objective
names appear in the Pareto-table header, without a separate redundant
`objectives:` summary line. The CLI displays cost-history calculation progress on
stderr while leaving the summary on stdout; an interactive progress frame is
overwritten in place and each stage leaves only its final line. The HV legend is
abbreviated as `HV (all & current gen.)`, and dense generation numbers alternate
between two heights. The time view combines elapsed time, failure
rate, execute-machine colors, and error occurrences. Average-time curves and each
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
either the individual row or its job metadata; the later batch recording timestamp
is only a last resort, so generation publication does not artificially cluster
failures at a boundary.

Individual view commands print a summary and create
`cost_YYYYMMDD_HHMMSS.png` or `time_YYYYMMDD_HHMMSS.png` by default.
`-o/--output` overrides the individual view's name or path; relative plot names are
written below `.yadof/tool_output/`. `view all` runs cost and time together, prints
both summaries, and creates both timestamped images. Use `--summary-only` to print
without creating PNGs. Destructive history clear requires interactive confirmation
or `--yes`, validates its exact workspace targets, clears only that workspace, and
recreates the jobs directory.

`view surrogate` is a separate, explicitly launched read-only tool. With no mode,
or with the explicit `gui` mode, it opens the selected workspace (or lets the user
choose one), explores saved surrogate checkpoint predictions and recorded real
evidence, and can calculate an in-memory cross-generation error audit. For each
rawData output it lists every dimension: select zero, one, or two as plot axes and
enter coordinates for the remaining dimensions. Each fixed dimension has both a
checkpoint-grid dropdown and an arbitrary finite-value entry. Stored values
preserve the checkpoint's original full-grid prediction path; off-grid values
directly query the same conditional INR and interpolate its stored per-coordinate
target scaler. The interactive plot then shows a scalar value, a curve, or a
filled two-dimensional color contour without contour lines. Recorded truth is
omitted for off-grid rawData positions because no such evidence exists. Continuous
task parameters remain independently queryable between recorded samples.

The two terminal modes are intended for people and AI agents that need analysis
without a window:

- `summary` does not load a model. It prints checkpoint generations/training
  metadata, completed-result counts by optimization generation, parameter ranges,
  objective names, and rawData dimension spans. `--format json` emits a
  schema-versioned machine-readable object.
- `audit` performs the same checkpoint inference and per-generation sampling as
  the GUI audit. It prints a matrix whose rows are optimization generations and
  columns are checkpoint generations. `--quantity` selects all costs, one named
  cost, all rawData, or one named rawData output; `--metric both` returns both
  aggregate matrices from the single inference pass. JSON represents missing
  finite aggregates as `null`. `--progress` writes status to stderr so stdout
  remains clean for text or JSON capture.

Both report modes default to the current directory when `--workspace` is omitted.
They write no PNG, cache, checkpoint, history, or other workspace file. The
surrogate tool never joins `view all`, starts a workflow, or changes training and
checkpoint artifacts. Install the `viewer` extra before using any of its modes.

## Python APIs

Every stateful public call takes a workspace:

```python
from yadof.evaluate_manager import evaluate_population, run_smoke_test
from yadof.optimize import run_generations

run_smoke_test("D:/work/study-a", mode="local")
run_generations("D:/work/study-a", 3, start_generation=0)
```
