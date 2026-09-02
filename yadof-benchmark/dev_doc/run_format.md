# Single-workspace execution format

The optional `top10_reference` cell field identifies a declared sequential paired
protocol. `benchmark_control.json` freezes the reference threshold before the
assisted command; `experiment_metrics/gNNNN.json` records each committed real
generation, and `oracle_audit/events.jsonl` is separate diagnostic evidence.
`result.json.top10_protocol` independently validates receipts and early completion
from durable formal rows. A `runtime_lock.json` can freeze installed file hashes.

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

The fully expanded `yadof.benchmark.spec` plan. The workflow stores preset
provenance and the selected declared/smoke budget profile. Each cell stores its
short ID, full `display_label`, semantic comparison/baseline/strategy/seed
identity, resolved budget, contracts,
execution policy, source digests, strategy entry path, and the destination-to-
source mapping for the complete declared strategy file set. The strategy digest
hashes ordered relative paths and file hashes, so a helper-only edit changes the
cell identity.

## `state.json`

The mutable `yadof.benchmark.state` record. Each cell directly stores status,
display label and raw identity fields, short paths, command paths, runtime,
active command, result, timestamps, and error. Each postprocessor directly stores
the same terminal information. There
are no attempt arrays or sealing states.

## Cell materialization

Before a cell starts, its selected baseline is copied to
`cells/cNNNN/workspace`; runtime directories are excluded and the selected
strategy entry becomes `submit/optimization.py`; every declared explicit-program
helper is copied to its relative path below `submit/`. For fast/local execution,
the baseline physical-core multiplier is resolved on the execution host and the
resulting worker cap is applied to that cell's `config.py`.

The cell's `state.json` entry records `physical_core_detection`,
`physical_cores`, `physical_core_multiplier`, `rounding`, and
`resolved_max_workers`. `spec.json` retains only the baseline multiplier, so a
plan is portable while each execution remains auditable.

The four command directories contain started/finished metadata, stdout, stderr,
and progress JSONL as applicable. A timed-out command records process-tree cleanup
and the scheduler continues independent cells when failure policy permits.
Visualization artifact names use the short cell ID only; human-facing reports
also carry the full display label.

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
