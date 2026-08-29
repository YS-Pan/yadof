# Run, evidence, and recovery

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
and exact read-only `inspect` command. It does not poll the child. `--hidden` is
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

The run publishes `results.json` and detailed `results.csv` at its root. Its
`reports/` directory contains:

- `summary.md`, with overall status, cell completion/validity, and final HV tables;
- `cell-validity.csv`;
- `final-hypervolume.csv`;
- `descriptive-results.json`, the bounded machine-readable report.

After each publication, timestamp-prefixed index directories below the benchmark
workspace's top-level `reports/` and `visualizations/` point back to this one
authoritative run root. Declared workflow postprocessors then run after every cell
has been collected and write additional run-local artifacts.

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

The generated comparison table is descriptive evidence. The package does not rank
strategies, apply significance tests, or make acceptance decisions.
