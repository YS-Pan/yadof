# 4+1 Physical View

## Checkout

Tracked inputs and code live below `benchmark_automation/`. Disposable assembly
state uses `.assembled/` and `.staging/`. Default generated runs live directly
under checkout `temp/<run-id>/`; an explicit `--runs-dir` may select another root.
Versioned experiment contracts live under `preregistrations/<registration-id>/`.
They may contain schema inventories, data-availability audits, unsealed threshold
templates and historical plans/receipts, but no generated run or design-row
evidence. Their committed files remain reviewable independently of ignored runtime
trees.

## Run layout

```text
<runs-dir>/<run-id>/
  run_spec.json
  matrix.json
  timing_history.json
  run_state.json
  inputs/execution/benchmark_runtime/
  inputs/baselines/<case>/workspace/
  inputs/strategies/<arm>/...
  inputs/histories/<case>/...
  cells/<cell-id>/attempts/<NNNN>/
    input_manifest.json
    workspace/
    commands/<NNNN-label>/
      command.started.json
      command.finished.json
      progress.jsonl
      stdout.log
      stderr.log
  visualizations/<baseline-id>/
  visualizations/viewcost/
  evidence/collect-<NNNN>/
  reports/report-<NNNN>/
  metrics.json
  report.json
  report.md
```

Specs, matrices, timing-history/input snapshots, attempts, command records,
evidence snapshots, and report snapshots are append-only. Run state and root
latest derived reports are atomically replaced. Inspection reads these files
without a lock; atomic publication and append-only command logs/events make that
safe. Run creation alone shallow-scans earlier immediate run directories;
inspection consumes only the frozen run-local timing snapshot.

The v1-v10 executable validators were deleted. Their recorded hash fields remain
non-authoritative historical provenance.

## Processes and streams

The foreground runner starts one yadof/postprocessor command at a time. Two child-
pipe threads write separate logs and enqueue display events. The foreground wait
loop consumes those events, appends timestamped progress JSON lines, and is the
sole Rich/interactive-stderr owner. A
detached visible Windows console owns the foreground runner; a later inspection
process is separate and read-only. Launcher-provided `TERM=dumb`/`unknown` is
ignored only by the Rich console after the stream itself proves interactive, so
the launcher environment cannot suppress live frames and child environments stay
intact.

## Retention

Git ignore status does not authorize deletion. Existing run evidence and active
logs remain user-owned. Code/doc tests use fresh pytest temporary roots outside the
repository and never reuse a live run directory.
