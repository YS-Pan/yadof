# Benchmark workspace

Create a workspace with `yadof-benchmark init PATH`. `PATH` supplies the parent and
human-readable semantic leaf. Unless that leaf already starts with a valid local
`YYYYMMDD_HHMMSS` prefix, the command creates
`<parent>/YYYYMMDD_HHMMSS-<semantic-leaf>` and prints the resolved path. Use that
returned path in later commands. An already timestamped target is not prefixed a
second time, and the command refuses to write into a non-empty resolved target.
The created layout is:

```text
YYYYMMDD_HHMMSS-SEMANTIC-PATH/
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
Once a run publishes results, the workspace top-level `reports/` and
`visualizations/` each receive a timestamp-prefixed run index directory that
points to those authoritative run-local artifacts. These indexes make the
initially empty output roots useful without copying or flattening the evidence.

The marker is tool-owned identity metadata, not a workflow configuration file.
Do not hand-edit it. The complete editable workflow is `benchmark.py`.

The generated `benchmark.py` is an inert but complete authoring scaffold. Its
comments show the required evidence class, run policy, a semantically named
algorithm strategy, baseline IDs, seed and budget fields, and a top-level
postprocessor. Replace those examples with the intended workflow and complete
`resources/.../optimization.py` modules before running `check`. Use `structural`
for fake/cheap smoke or bounded canaries and `performance` only for a deliberately
authorized performance campaign; the package never infers this classification
from population or generation counts. It does reject a declared performance
comparison below 100 individuals per generation or below 20 generations. The
scaffold's 12 × 3 example is explicitly structural-only. A single-seed
performance comparison remains allowed for algorithm iteration, but its plan and
results are marked exploratory.

Packaged baselines are version-matched read-only resources. To edit a task, copy
its complete semantic source directory into a separate baseline collection, keep
the `provider/task` directory equal to the manifest ID, and select that collection
with `--baselines-root` or `baselines_root=`. A new run snapshots the edited source;
later edits affect only later runs.

After editing, use `check` or `plan`. Both are read-only with respect to benchmark
runs, but both execute top-level Python imports and `build_benchmark()`.
