# 4+1 Physical View

## Checkout

Tracked inputs and code live below `benchmark_automation/`. Disposable assembly
state uses `.assembled/` and `.staging/`. Default generated runs live directly
under checkout `temp/<run-id>/`; an explicit `--runs-dir` may select another root.

## Run layout

```text
<runs-dir>/<run-id>/
  run_spec.json
  matrix.json
  run_state.json
  inputs/baselines/<case>/workspace/
  cells/<cell-id>/attempts/<NNNN>/
    input_manifest.json
    workspace/
    commands/<NNNN-label>/
      command.started.json
      command.finished.json
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

Specs, matrices, snapshots, attempts, command records, evidence snapshots, and
report snapshots are append-only. Run state and root latest derived reports are
atomically replaced. Inspection reads these files without a lock; atomic
publication and append-only command logs make that safe.

## Processes and streams

The foreground runner starts one yadof/postprocessor command at a time. Two child-
pipe threads write separate logs and enqueue display events. The foreground wait
loop consumes those events and is the sole Rich/interactive-stderr owner. A
detached visible Windows console owns the foreground runner; a later inspection
process is separate and read-only.

## Retention

Git ignore status does not authorize deletion. Existing run evidence and active
logs remain user-owned. Code/doc tests use fresh pytest temporary roots outside the
repository and never reuse a live run directory.
