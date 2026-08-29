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
├── timing_history.json           # bounded frozen prior-cell timing snapshot
├── benchmark.log                 # lifecycle/progress/final status
├── spec.json
├── state.json
├── results.json
└── results.csv
```

Every command attempt keeps immutable `started.json`/`finished.json`, separate
`stdout.log`/`stderr.log`, and append-only `progress.jsonl`. The progress stream
timestamps command activity and parsed generation snapshots; raw child lines remain
only in their stream logs unless explicit CLI/API streaming is requested.

The specification digest excludes only the creation timestamp and includes the
workflow and driver digests. Loading fails closed on format, identity, JSON, or
digest mismatch. `state.json` is atomically replaced after every transition.
Every human-visible run ID begins with local `YYYYMMDD_HHMMSS`; user-provided IDs
are semantic suffixes unless they already carry that prefix.

The frozen workflow and every serialized cell carry the explicit evidence class.
Result JSON, detailed/result CSV rows, descriptive report rows, Markdown summary,
workspace indexes, detached-launch receipt, and inspect repeat that class and its
fixed scope notice.
Historical runs without the field are inspectable as `unclassified` and are never
eligible for performance conclusions.

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

`benchmark.log` is append-only presentation evidence for foreground and detached
launches. Per-command stdout/stderr remain separated below the relevant attempt.
The interactive CLI shows exactly two Rich-owned live rows (active cell, then
global benchmark); lifecycle output is printed above them. Background pipe readers
never render: they enqueue parsed yadof generation snapshots and the foreground
owner turns those into timestamped progress events. Non-TTY output is bounded and
the synchronous Python API never blocks for terminal input.

Run state records initial host/Python/hashed resource identity plus run start and
terminal timestamps. `timing_history.json` contains at most 256 completed-cell
records found before run creation, without changing those earlier runs. Inspect
adds completed cells from the current run in memory, selects at most five recent
same-baseline/same-strategy/same-budget matches, distinguishes exact snapshot/config
identity from compatible identity, and never uses another strategy as a point
estimate. Three or more timestamped completed generations enable a non-negative
generation-duration trend for nonlinear late-stage ETA. Inspect itself writes
nothing and bounds anomaly/evidence disclosure.
