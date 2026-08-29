# Run format and recovery

A run uses format `yadof.benchmark.workflow-run` and contains:

```text
RUN/
├── driver/{api.py,cli.py,benchmark_runtime/...}
├── inputs/
│   ├── workflow/{benchmark.py,resources/...}
│   ├── baselines/.../workspace/
│   └── strategies/.../optimization.py
├── cells/CELL/attempts/NNNN/       # readable command/result evidence
├── workspaces/CELL_DIGEST/NNNN/    # materialized yadof execution workspace
├── postprocessing/ID/attempts/NNNN/
├── visualizations/
│   ├── cost/CELL--attempt-NNNN.png
│   └── BASELINE-SLUG/CELL--attempt-NNNN--...
├── reports/
│   ├── summary.md
│   ├── cell-validity.csv
│   ├── final-hypervolume.csv
│   └── descriptive-results.json
├── temp/
├── spec.json
├── state.json
├── results.json
└── results.csv
```

The specification digest excludes only the creation timestamp and includes the
workflow and driver digests. Loading fails closed on format, identity, JSON, or
digest mismatch. `state.json` is atomically replaced after every transition.
Every human-visible run ID begins with local `YYYYMMDD_HHMMSS`; user-provided IDs
are semantic suffixes unless they already carry that prefix.

A cell progresses through planned, checked, running, succeeded, and collected.
Interrupted checked/running attempts are sealed and the cell returns to planned.
Failed cells receive a new attempt. Collection failure preserves successful
execution so resume retries collection without rerunning the simulator.

After successful measured execution, collection is followed by two mandatory
run-owned commands: an explicit-output `yadof view cost` and the snapshotted
baseline `postprocess.py`. Cost history is grouped once under `visualizations/cost`;
domain artifacts share one semantic directory per baseline and use cell/attempt
prefixes. A missing script, failed command, missing cost image, or empty domain
output marks the attempt/cell failed, preserves its result and issue, and prevents
overall success.

The full semantic cell ID remains in `cells/` and state. The materialized yadof
workspace uses the first 16 hexadecimal characters of the cell ID's SHA-256 digest
plus the attempt number. This compact run-local path reduces Windows path pressure
for external simulators while the attempt record points to it explicitly. Every
measured `yadof run` also uses `--fail-on-all-infinite`; a generation with no finite
candidate therefore fails the cell instead of producing an empty collected result.

After all cells are collected, the current descriptive result set is published and
the run enters postprocessing. Each callback gets a fresh attempt and a
`PostprocessContext`. Successful callbacks are skipped on resume; failed or
interrupted callbacks retry without touching collected cells. The run is complete
only when every cell is collected and every declared postprocessor succeeds.

Each result publication also refreshes the timestamped workspace-level report and
visualization index directories while the originating benchmark workspace remains
available. They contain paths/status only and always lead back to this single
authoritative run root; recovery correctness does not depend on them.

Run-owned recovery dynamically loads `driver/benchmark_runtime`; it never replans
the original workspace or depends on current package implementation details.
