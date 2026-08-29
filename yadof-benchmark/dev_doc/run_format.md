# Single-workspace execution format

Despite this source filename, the current storage model has no separate run
directory. The benchmark workspace itself contains one execution:

```text
WORKSPACE/
├── runtime.json
├── spec.json
├── state.json
├── results.json
├── results.csv
├── benchmark.log
├── cells/
│   └── c0001/
│       ├── baseline.json
│       ├── workspace/
│       ├── commands/
│       │   ├── 01-check/
│       │   ├── 02-run/
│       │   ├── 03-view-cost/
│       │   └── 04-postprocess/
│       └── result.json
├── postprocessing/
│   └── ID/
│       ├── result.json
│       └── user outputs
├── reports/
├── visualizations/
│   ├── cost/c0001.png
│   └── domain/c0001--...
└── temp/
```

There is no `driver/`, `inputs/`, `workspaces/`, `runs/`,
`attempts/0001/`, or `timing_history.json`.

## `runtime.json`

Written once before execution. Records yadof-benchmark and yadof versions, Python
version/interpreter, UTC timestamp, platform, node, and process user. It is
provenance, not an upgrade/resume compatibility marker.

## `spec.json`

The fully expanded `yadof.benchmark.spec` plan. Each cell stores its short ID and
semantic comparison/baseline/strategy/seed identity, resolved budget, contracts,
execution policy, source digests, and strategy source path.

## `state.json`

The mutable `yadof.benchmark.state` record. Each cell directly stores status,
short paths, command paths, runtime, active command, result, timestamps, and
error. Each postprocessor directly stores the same terminal information. There
are no attempt arrays or sealing states.

## Cell materialization

Before a cell starts, its selected baseline is copied to
`cells/cNNNN/workspace`; runtime directories are excluded and the selected
strategy becomes `submit/optimization.py`. Fast/local worker settings are
applied to that cell's `config.py`.

The four command directories contain started/finished metadata, stdout, stderr,
and progress JSONL as applicable. Visualization artifact names use the short cell
ID only.

## Publication

After a terminal cell, aggregate results and reports are atomically republished
before a FIFO scheduler slot is refilled. A required visualization is part of
collection. Optional workflow postprocessors run once only after all cells
collect.

Final status is `completed` only when every cell is collected and valid and all
registered workflow postprocessors succeed. Individual failed/non-finite
simulations can be tolerated by the validity rule documented in
[architecture.md](architecture.md).

There is no resume transition. A failed or interrupted execution remains evidence
in its workspace; another attempt is a newly initialized workspace.
