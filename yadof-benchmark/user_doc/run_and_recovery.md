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

Run `yadof-benchmark check --workspace PATH` before committing compute. It imports
`benchmark.py`, validates every complete strategy module and baseline ID, expands
all comparison cells, calculates input digests, and writes nothing.

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

Use `inspect --run RUN_PATH` for a read-only status view. Use `resume --run
RUN_PATH` after interruption or failure. Resume loads the run-owned driver and
input snapshots. Successful cells and postprocessors are skipped; interrupted or
failed work receives a new attempt. External edits to the original workspace do
not change an existing run.

The generated comparison table is descriptive evidence. The package does not rank
strategies, apply significance tests, or make acceptance decisions.
