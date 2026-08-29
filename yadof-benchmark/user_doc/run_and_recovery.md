# Run, evidence, and recovery

## Evidence classes and execution ladder

Every run freezes the workflow's explicit evidence class. `structural` covers
fake/cheap runner tests, CLI smoke, adapter integration checks, and bounded
canaries. Even when it follows real configuration and simulator paths, it proves
only that the workflow is structurally operable; its plan, cell rows, indexes,
inspect output, and reports say that it must not support algorithm performance
conclusions. `performance` identifies a deliberately measured campaign, but its
outputs remain descriptive and do not rank strategies or decide acceptance.

Package pytest, deterministic event replay, and recovery/fault injection are
separate engineering evidence. Recovery proves that attempts, snapshots, and
resume semantics work; it is not an optimization performance benchmark. The
package test suite registers `structural` and `recovery` pytest markers so these
claims can be reviewed separately.

Before committing a long performance campaign:

1. Run bounded `check` or `plan` and review the explicit evidence class and budget.
2. Smoke each selected real adapter through its source yadof workspace under the
   current simulator execution policy.
3. Complete a bounded `evidence="structural"` canary using the same baseline IDs,
   complete strategy modules, interpreter, and external configuration paths as the
   intended full run.
4. If benchmark orchestration is incompatible, fix it and repeat the structural
   ladder before requesting the full run. If the smoke instead exposes a yadof
   framework defect, record a separate root `dev_doc/toDo/` handoff and do not
   start the affected performance campaign.
5. Start the `evidence="performance"` run only with the execution authority
   required by the current yadof user documentation.

`check` and `plan` do not execute a simulator. Adapter smoke and a structural
canary are measured work, so their small size does not bypass execution authority.

## Performance scale, difficulty, and seeds

A performance cell has a hard minimum of 100 individuals per generation and 20
generations: 2000 planned real evaluations. Workflow loading rejects either lower
dimension even when their product reaches 2000, and points the author to
`evidence="structural"` for a smaller smoke or canary. This guard prevents the
former few-generation, dozen-individual pattern from silently producing a
performance report.

The minimum is not a task-difficulty target. Before using a baseline to compare a
surrogate strategy, run a complete non-surrogate NSGA-III reference and adjust the
task so convergence is nearer roughly 10000 evaluations; 200 × 50 is the
historical reference shape, not another hard guard. If the reference solves the
task easily by about 2000 evaluations, the surrogate comparison is not yet
informative enough and the baseline should be made harder before the multi-strategy
campaign.

For rapid algorithm debugging, a performance comparison may use one explicit seed
per state/arm. Plan, cell, CSV/JSON, Markdown, workspace-index, and inspect output
mark that scope `exploratory`; it cannot stand in for a robust conclusion. Stronger
campaigns use multiple explicit seeds. The list is fully configurable: the three
seeds used by earlier three-baseline campaigns are historical practice, not a
scientific constant enforced by the tool. Multi-seed output remains descriptive
and does not automatically claim significance or robustness.

## Visible execution is the default

Every measured `run` or `resume` should have a visible process window, regardless
of whether a human or an AI agent starts it. Run directly in the foreground when
the caller already owns a visible terminal. When an AI agent must detach a long
Windows run from its own task process, use the built-in detached launcher:

```powershell
yadof-benchmark run --workspace PATH --run-id RUN_ID --detach
yadof-benchmark resume --run RUN_PATH --detach
```

On Windows, `--detach` opens a separate normal console and immediately returns a
bounded JSON receipt containing the PID, resolved run path, `benchmark.log` path,
exact read-only `inspect` command, and frozen evidence class/scope notice. It does
not poll the child. `--hidden` is
accepted only together with `--detach` and only when the user explicitly requests
the hidden exception; that receipt also names the redirected stdout/stderr logs.
The child breaks away from an automation host's command-lifetime job, so returning
the receipt does not terminate the benchmark.
Use an equivalent caller-owned visible terminal or terminal-multiplexer pane on
other systems. Output redirection is not the visible default because it removes
live progress from the process window.

Foreground `run` and `resume` keep two Rich-owned rows at the bottom of an
interactive terminal: the active cell first and the global benchmark second.
Lifecycle and command messages appear above those rows. The active-cell row is
fed by real generation snapshots from the yadof child, so it exposes intermediate
evaluation/success/error counts rather than staying at zero until command exit.
Narrow terminals use shorter labels while retaining evaluation, generation,
success/error, and global completion/failure counts. An inherited `TERM=dumb`
does not disable refresh in a real TTY, while `NO_COLOR` remains respected. Plain
non-TTY output uses bounded snapshots and never waits for keyboard input.

Every child command writes separate `stdout.log` and `stderr.log` files below its
attempt, and raw child output is not echoed by default. Add
`--stream-child-output` to `run` or `resume` only for a deliberate live diagnostic;
the foreground terminal owner then prints `child-output` events above the two Rich
rows while retaining the same log files.

Run `yadof-benchmark check --workspace PATH` before committing compute. It imports
`benchmark.py`, validates every complete strategy module and baseline ID, expands
all comparison cells, calculates input digests, and writes nothing.

`check` and `plan` print a bounded overview of comparison/cell/evaluation counts,
selected semantic IDs, and budget ranges. Add `--json` to either command to print
the complete expanded `RunSpec`, including every cell. The default is intended for
both people and agents and does not grow in proportion to a large comparison
matrix.

`run` creates a new immutable run directory below the workflow's `runs_dir`. The
human-visible run leaf always starts with local `YYYYMMDD_HHMMSS`; an explicit
`--run-id` supplies the semantic suffix and is automatically prefixed unless it is
already timestamped. The run snapshots:

- `benchmark.py` and `resources/`;
- every selected baseline workspace and manifest;
- every selected complete `optimization.py`;
- `api.py`, `cli.py`, and the bounded runtime driver used for recovery;
- the exact expanded `spec.json` and evolving `state.json`.

Each cell receives a new attempt directory. The tool checks the materialized yadof
workspace, runs it, collects results through public yadof APIs, renders the
equivalent of `yadof view cost`, and invokes the snapshotted baseline
`postprocess.py`. Cost plots are grouped below `visualizations/cost/`; domain
outputs are grouped into one semantic directory per baseline, such as
`visualizations/chrono-trebuchet/`, rather than one top-level directory per cell.
The cell is collected only when both required visualization stages exit
successfully and create non-empty artifacts.

Structural workflows stop after the first failed or invalid cell by default.
Performance workflows continue independent cells by default so an expensive
failure does not erase the chance to retain other evidence. `fail_fast=` may override that
scheduling choice, but it never weakens completion: any failed, incomplete,
all-infinite, or collected-but-invalid cell leaves the overall status unsuccessful
and makes the CLI exit nonzero.

The run publishes `results.json` and detailed `results.csv` at its root. Its
`reports/` directory contains:

- `summary.md`, with cell validity, paired fairness, final HV/HV-AUC, cross-seed
  aggregates, and surrogate-training summaries;
- `cell-validity.csv`, including planned/attempted/completed/finite counts and the
  generation-0 population fingerprint;
- `final-hypervolume.csv`;
- `hypervolume-trajectory.csv`, aligned by cumulative attempted real evaluations;
- `pairing-validity.csv`;
- `cross-seed-aggregates.csv`;
- `surrogate-training.csv`;
- `descriptive-results.json`, the bounded machine-readable report.

Planned is the frozen population × generation budget. Attempted counts durable
logical candidate records, not transport retries; completed counts successful
records; finite counts completed rows whose objective tuple is usable for HV.
Final HV, the cumulative HV trajectory, and trapezoidal HV-AUC are descriptive.
Failures, non-finite costs, or an incomplete cell make validity/completeness fail
instead of becoming a performance score. Incomplete and mismatched-pair evidence
stays in its run, while cross-seed aggregates name and exclude the affected seed.

Optimizer wall time remains operational timing evidence, not a main comparison
metric. Surrogate-training duration is reported separately and, only when the
workflow configured an external representative expensive-generation duration,
shown as a descriptive ratio to that reference. Peak resources and checkpoint
size are not benchmark acceptance metrics.

These artifacts, the workspace indexes, and read-only inspect repeat the frozen
evidence class, replication scope, and their notices. A copied CSV row therefore
remains classified outside its original run directory.

After each publication, timestamp-prefixed index directories below the benchmark
workspace's top-level `reports/` and `visualizations/` point back to this one
authoritative run root. Declared workflow postprocessors then run after every cell
has been collected and write additional run-local artifacts.

Publication is a hard boundary between cells. The next simulation does not start
until aggregate results, reports, and available indexes have returned from atomic
publication. A storage/publication exception stops the campaign immediately and is
recorded in `state.json` when state storage remains available. Use that diagnostic
and immutable attempt results on resume; a storage error is never converted into a
cell score or ignored for throughput. Inside yadof, the campaign recorder applies
the same stronger rule to candidate evidence: bounded backpressure delays later
simulation until accepted evidence is published, and `RecordingError` is fatal.

Run-level lifecycle/progress/final-status evidence is appended to
`benchmark.log`. Human-readable command and result evidence remains below
`cells/<cell-id>/attempts/<number>/`. The actual yadof execution workspace is stored
at a compact run-local `workspaces/<cell-digest>/<number>/` path and is referenced
by the attempt state. The shorter physical path protects file-oriented Windows
simulators from avoidable path-length failures without hiding the semantic
cell ID. A measured command rejects an all-infinite generation, so a cell with no
finite evaluation is failed and remains eligible for a later `resume` attempt.

## Read-only inspection and ETA

Use `inspect --run RUN_PATH` for the bounded first view. It does not update state,
replan the workspace, resume work, or rewrite timing history. The summary reports:

- run/cell/postprocessor status and the active phase;
- completed/valid/invalid/incomplete counts and comparison-result availability;
- at most eight anomalies plus an explicit truncated count;
- total elapsed time, active-cell runtime, last activity, inactivity, estimated
  remaining seconds, UTC completion time, confidence, and evidence;
- exact commands and paths for the next disclosure step.

Each new run freezes `timing_history.json` from bounded completed-cell records in
earlier sibling runs. An **exact** timing match uses the same comparison task,
baseline and strategy semantic IDs, population/generations, baseline and strategy
snapshots, execution configuration, workflow/driver identity, Python, host, and
hashed external-resource identity. A **compatible** match keeps the same baseline,
strategy, budget, task, execution configuration, Python, and host while allowing
driver/workflow/strategy source identity to differ. Compatible evidence is lower
confidence. A different strategy is never used as a point estimate, even for the
same baseline.

The estimator uses at most the five most recent matches and reports their median,
sample count, relative MAD, match level, and source runs. During an active cell,
timestamped generation events replace a whole-cell linear progress assumption once
three generations have completed: a non-negative generation-duration trend can
represent later surrogate training becoming slower. Baseline
`evaluation_seconds × remaining evaluations` is only a low-confidence lower bound
and explicitly excludes optimizer or surrogate-training overhead. A failed terminal
run has no asserted completion ETA because resume creates new attempts.

Follow this progressive disclosure order:

1. read `inspect`;
2. read `reports/summary.md`;
3. select fields from `reports/descriptive-results.json`;
4. read one active or failed cell's `stdout.log`/`stderr.log`;
5. select only the necessary detailed fields from `results.json`.

Use `resume --run RUN_PATH` after interruption or failure. Resume loads the
run-owned driver and input snapshots. Successful cells and postprocessors are
skipped; interrupted or failed work receives a new attempt. External edits to the
original workspace do not change an existing run.

Each attempt has a separate `attempt.json`; every command keeps separate
`stdout.log` and `stderr.log`. Interrupted/failed execution is sealed with
`completeness=incomplete`, keeps its old compact workspace and raw files, and is
retried in a new numbered attempt/workspace. A collected attempt is sealed
complete. A collection-only failure after successful simulator execution retries
collection on that same open attempt rather than rerunning the simulator. Resume
revalidates the run-owned driver, workflow/resources, baseline, and strategy
digests; mutation inside an old run fails closed, while editing reusable baseline
or workflow sources remains valid for a new run.

The generated comparison table is descriptive evidence. The package does not rank
strategies, apply significance tests, or make acceptance decisions.
