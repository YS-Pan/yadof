# Run, evidence, and recovery

Run `yadof-benchmark check --workspace PATH` before committing compute. It imports
`benchmark.py`, validates every complete strategy module and baseline ID, expands
all comparison cells, calculates input digests, and writes nothing.

`run` creates a new immutable run directory below the workflow's `runs_dir`. It
snapshots:

- `benchmark.py` and `resources/`;
- every selected baseline workspace and manifest;
- every selected complete `optimization.py`;
- `api.py`, `cli.py`, and the bounded runtime driver used for recovery;
- the exact expanded `spec.json` and evolving `state.json`.

Each cell receives a new attempt directory. The tool checks the materialized yadof
workspace, runs it, collects results through public yadof APIs, and publishes
`results.json`, `results.csv`, and `reports/summary.md`. Declared postprocessors run
after collection and write to run-local output directories.

Use `inspect --run RUN_PATH` for a read-only status view. Use `resume --run
RUN_PATH` after interruption or failure. Resume loads the run-owned driver and
input snapshots. Successful cells and postprocessors are skipped; interrupted or
failed work receives a new attempt. External edits to the original workspace do
not change an existing run.

The generated comparison table is descriptive evidence. The package does not rank
strategies, apply significance tests, or make acceptance decisions.
