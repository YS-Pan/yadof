# Benchmark workspace

Create a workspace with `yadof-benchmark init PATH`. The command refuses to write
into a non-empty directory and creates this layout:

```text
PATH/
├── .benchmark/workspace.json
├── benchmark.py
├── resources/
├── runs/
├── visualizations/
├── reports/
└── temp/
```

`benchmark.py` is user-owned executable workflow code. `resources/` holds complete
strategy modules and any other inputs used while building the workflow. `runs/`
holds immutable run directories. The three remaining top-level directories are
available for workspace-level summaries; authoritative output for a particular run
lives in that run's own `visualizations/`, `reports/`, and `temp/` directories.

The marker is tool-owned identity metadata, not a workflow configuration file.
Do not hand-edit it. The complete editable workflow is `benchmark.py`.

After editing, use `check` or `plan`. Both are read-only with respect to benchmark
runs, but both execute top-level Python imports and `build_benchmark()`.
