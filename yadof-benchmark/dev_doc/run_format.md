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
│   ├── attempt.json                # independent lifecycle/completeness metadata
│   └── commands/.../{stdout.log,stderr.log,...}
├── workspaces/CELL_DIGEST/NNNN/    # materialized yadof execution workspace
├── postprocessing/ID/attempts/NNNN/
├── visualizations/
│   ├── cost/CELL--attempt-NNNN.png
│   └── BASELINE-SLUG/CELL--attempt-NNNN--...
├── reports/
│   ├── summary.md
│   ├── cell-validity.csv
│   ├── final-hypervolume.csv
│   ├── hypervolume-trajectory.csv
│   ├── pairing-validity.csv
│   ├── cross-seed-aggregates.csv
│   ├── surrogate-training.csv
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
`attempt.json` is atomically refreshed while the attempt is active. Once it records
`sealed=true`, any later metadata change fails closed instead of rewriting evidence.

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

Each collected cell records planned, attempted, completed, and finite evaluation
counts. Attempted means one durable logical candidate record, not an internal
transport retry. The ordered normalized generation-0 population is fingerprinted;
the fingerprint is published only when every planned generation-0 index and vector
is present. Cumulative HV trajectory points use cumulative attempted real
evaluations as their x coordinate, and HV-AUC is trapezoidal area from `(0, 0)`;
the normalized form divides by final attempted count.

For each comparison/baseline/seed group, pairing validation requires matching
baseline snapshot digests, planned and attempted budgets, complete matching
generation-0 fingerprints, and individually valid cells. Invalid pairs retain all
run/cell evidence but publish no reference delta. Cross-seed descriptive aggregates
include only valid cells from valid pairs and list every excluded seed explicitly.
Failures, non-finite objectives, and incomplete counts are validity/completeness
facts, not a performance score. Reports never rank arms, test significance, or
make acceptance decisions.

Surrogate-training events are copied from public yadof metadata and summarized in
their own report. When the frozen workflow supplies an external representative
expensive-generation duration, the report includes the maximum-duration/reference
ratio. Optimizer wall time remains operational timing evidence rather than a main
comparison metric; peak resources and checkpoint size are not acceptance metrics.

Every new cell also carries its comparison's replication scope. A single-seed
performance comparison is `exploratory`; a performance comparison with two or
more explicit seeds is `multi-seed`; structural comparisons use `structural`.
Plan summaries, result rows, CSV/JSON reports, Markdown, workspace indexes, and
inspect repeat the scope and its fixed notice so a single-seed result cannot be
detached from its exploratory boundary.

A cell progresses through planned, checked, running, succeeded, and collected.
Interrupted checked/running attempts are sealed with `completeness=incomplete` and
the cell returns to planned. Failed attempts are sealed incomplete; collected
attempts are sealed complete. Failed cells receive a new numbered attempt and a
new compact execution workspace without deleting or reusing the old path.
Collection failure preserves a successful, not-yet-sealed execution so resume
retries collection without rerunning the simulator.

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
only when every cell is collected, every cell validity contract passes, and every
declared postprocessor succeeds. Structural workflows default to fail-fast;
performance workflows default to continuing independent cells, but either class
finishes non-successfully when any cell is invalid or incomplete.

Publication after each cell is a synchronous recovery boundary: another cell is
not started until aggregate results, reports, and available workspace indexes have
been atomically refreshed. A publication exception stops the campaign immediately,
records its UTC/boundary/error in `state.json` when possible, and remains a raised
error rather than an ordinary cell failure. Resume may republish from immutable
attempt results; no accepted raw evidence is discarded for aggregate throughput.

Each result publication also refreshes the timestamped workspace-level report and
visualization index directories while the originating benchmark workspace remains
available. They contain paths/status only and always lead back to this single
authoritative run root; recovery correctness does not depend on them.

Run-owned recovery dynamically loads `driver/benchmark_runtime`; it never replans
the original workspace or depends on current package implementation details. Each
execution also revalidates run-owned driver, workflow/resources, baseline, and
strategy digests. External edits affect a later snapshot only; mutation inside an
existing run fails closed.

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
