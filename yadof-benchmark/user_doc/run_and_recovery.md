# Run, evidence, and recovery

## Visible execution is the default

Every measured `run` or `resume` should have a visible process window, regardless
of whether a human or an AI agent starts it. Run directly in the foreground when
the caller already owns a visible terminal. When an AI agent must detach a long
Windows run from its own task process, start a separate normal console and report
the returned process ID. For example:

```powershell
$benchmarkExe = (Get-Command yadof-benchmark).Source
$workspace = (Resolve-Path -LiteralPath "PATH").Path
$process = Start-Process -FilePath $benchmarkExe `
  -ArgumentList @(
    "run", "--workspace", ('"' + $workspace + '"'),
    "--run-id", "RUN_ID"
  ) `
  -WorkingDirectory $workspace `
  -WindowStyle Normal `
  -PassThru
$process.Id
```

Use the equivalent visible terminal or terminal-multiplexer pane on other systems.
Do not use `-WindowStyle Hidden`, `CREATE_NO_WINDOW`, `SW_HIDE`, or another hidden
launcher unless the user explicitly requests a hidden run. Output redirection is
also not the default because it removes live progress from the process window;
durable per-command logs, state, and results remain inside the run directory.

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

Human-readable command and result evidence remains below
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
