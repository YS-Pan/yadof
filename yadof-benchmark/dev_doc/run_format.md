# Run format and recovery

A run uses format `yadof.benchmark.workflow-run` and contains:

```text
RUN/
├── driver/{api.py,cli.py,benchmark_runtime/...}
├── inputs/
│   ├── workflow/{benchmark.py,resources/...}
│   ├── baselines/.../workspace/
│   └── strategies/.../optimization.py
├── cells/CELL/attempts/NNNN/
├── postprocessing/ID/attempts/NNNN/
├── visualizations/
├── reports/summary.md
├── temp/
├── spec.json
├── state.json
├── results.json
└── results.csv
```

The specification digest excludes only the creation timestamp and includes the
workflow and driver digests. Loading fails closed on format, identity, JSON, or
digest mismatch. `state.json` is atomically replaced after every transition.

A cell progresses through planned, checked, running, succeeded, and collected.
Interrupted checked/running attempts are sealed and the cell returns to planned.
Failed cells receive a new attempt. Collection failure preserves successful
execution so resume retries collection without rerunning the simulator.

After all cells are collected, the current descriptive result set is published and
the run enters postprocessing. Each callback gets a fresh attempt and a
`PostprocessContext`. Successful callbacks are skipped on resume; failed or
interrupted callbacks retry without touching collected cells. The run is complete
only when every cell is collected and every declared postprocessor succeeds.

Run-owned recovery dynamically loads `driver/benchmark_runtime`; it never replans
the original workspace or depends on current package implementation details.
