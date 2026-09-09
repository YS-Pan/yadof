# Single-workspace execution format

The optional `top10_reference` cell field identifies a declared dependency-ordered paired
protocol. `benchmark_control.json` freezes the reference threshold before the
assisted command; `experiment_metrics/gNNNN.json` records each committed real
generation, and `oracle_audit/events.jsonl` is separate diagnostic evidence.
`result.json.top10_protocol` independently validates receipts and early completion
from durable formal rows. A `runtime_lock.json` can freeze installed file hashes.

Cells resolve `population`, `batch_size`, `initial_population` and `generations`
from strategy overrides, then comparison values, with B/I defaulting to the
resolved P. Planned formal attempts are I + (G - 1) B. Old records omitting B/I
retain their P defaults. Every later CLI command carries the resolved sizes.
Collection checks initial-design size I and independently validates the number
of formal rows per generation, including failed attempts. Reference pairing is
by comparison/baseline/seed across distinct P/B/G settings with equal budgets.
The scheduler admits a dependent cell only after publishing its reference result;
unrelated ready cells continue up to the declared concurrency cap.

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

An unhandled scheduler failure adds `execution_error={utc, error}`, marks the
workspace failed, and clears active commands after cancellation has joined the
workers. Cells that had started but could not reach a terminal status are marked
failed; unstarted cells remain planned. `inspect` reports the workspace cause
before secondary cell anomalies. A persistent storage failure can prevent this
final state write; the nonzero process exit and its error log remain authoritative.

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

An internal resource-calibration policy may override capacity at cell admission.
In that case `state.json.capacity_history` records numbered decisions with UTC,
completed-cell count, physical cores, active-cell limit, baseline multipliers,
and reason. `effective_cell_concurrency` is the current admission limit. Each
cell state/result records its `capacity_revision` and resolved
`simulation_concurrency`. These overrides do not alter `spec.json` or an already
materialized cell. They cannot change scientific inputs or omit planned cells.

The four command directories contain started/finished metadata, stdout, stderr,
and progress JSONL as applicable. A timed-out command records process-tree cleanup
and the scheduler continues independent cells when failure policy permits.
Command `started.json` records only the selected `native_thread_limits`, not the
full potentially sensitive environment. `state.json.resource_protection` records
initial/latest physical and committed memory, reserve fractions, the Windows job
commit ceiling, and any memory-watchdog failure. Memory exhaustion is a fatal
workspace boundary regardless of ordinary cell failure policy.
Visualization artifact names use the short cell ID only; human-facing reports
also carry the full display label.

## Publication

After a terminal cell, aggregate results and reports are atomically republished
before a scheduler slot admits the next dependency-ready cell. A required visualization is part of
collection. Optional workflow postprocessors run once only after all cells
collect by default. A `run_on_failure=true` declaration in
`spec.json.workflow.postprocessors` instead permits a callback after scheduling
ends with failed/incomplete cells. In that case ordinary callbacks have
`status=skipped`, a finish timestamp and a `skip_reason`. Publication failures
remain fatal and do not invoke callbacks against incomplete published evidence.

Final status is `completed` only when every cell is collected and valid and all
registered workflow postprocessors succeed. Individual failed/non-finite
simulations can be tolerated by the validity rule documented in
[architecture.md](architecture.md).

There is no resume transition. A failed or interrupted execution remains evidence
in its workspace; another attempt is a newly initialized workspace.
