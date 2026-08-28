# Simplify benchmark and hierarchical CAE structure

## Why

The source-checkout benchmark combined 4,887 lines of planning, storage, state,
execution, progress, collection, reporting, and timing in one module. Eight failed
experiment runners added 7,254 duplicated lines and historical validators treated
current source/wheel/artifact hashes as execution gates. Hierarchical CAE likewise
combined network, objective, training, inference, runtime, and metadata concerns.

## What changed

- `benchmark_core.py` became a compatibility facade over eight bounded
  `benchmark_runtime` services. New runs copy and execute a complete run-local
  runtime snapshot plus selected baseline, strategy, and history inputs.
- Resume no longer compares current config/package/source/artifact hashes. Digests
  remain provenance. Unfinished legacy runs without a complete execution snapshot
  require explicit restart/migration; completed legacy evidence remains readable.
- The eight legacy `hierarchical_cae_*.py` runners and thirteen v1-v10 executable
  validator/result-validator files were deleted. Historical JSON plans/receipts and
  their original conclusions remain unchanged. No successor experiment engine was
  created because this structural task introduced no new scientific experiment.
- Hierarchical CAE now separates networks, objectives, training, inference, data
  adaptation, state repository, and projection behind a narrow runtime facade.
  The former `modeling.py` and component-local `metadata.py` were deleted.
- Conditional-INR and CAE share atomic artifact publication, bounded training-event
  recording, and deterministic finite-member selection. Checkpoint namespaces,
  semantic identity, schemas, quality policy, and schedulers remain component-local;
  scheduler sharing was rejected because the policies are not behavior-equivalent.
- Viewer imports, wheel-member expectations, historical-result tests, architecture,
  blueprints, terminology, operator/developer docs, and active successor toDos were
  synchronized. No threshold, Gate 0 conclusion, simulator evidence, or default
  strategy changed.

## Legacy source provenance

- calibration checkpoint/calibration/dataset:
  `d845c57aedce4f8e0ee77925f72bd8cadf5fd973`
- experimental assessment:
  `f8a684f39e3b85469d33c15085e7e877e7c6ca35`
- experimental offline:
  `df17efbff8e9b2f44c0a672b1fd0d59aeeb83ed9`
- Gate 4/validation v1/validation:
  `318963356882b0e9805d4e5aa8d9c7a5bdb71d72`

## Machine-readable size report

Physical lines are counted at task-start `HEAD` and in the completed working tree.
Historical JSON means all 31 preregistration JSON records; those records were not
rewritten or moved.

```json
{
  "before": {
    "generic_runner": 4887,
    "legacy_runners": 7254,
    "hierarchical_cae": 5042,
    "active_subtotal": 17183,
    "benchmark_tests": 2898,
    "historical_preregistration_json": 5298,
    "validators": 2731
  },
  "after": {
    "generic_runner": 2815,
    "legacy_runners": 0,
    "hierarchical_cae": 3131,
    "active_subtotal": 5946,
    "benchmark_tests": 2610,
    "historical_preregistration_json": 5298,
    "validators": 0
  },
  "counts": {
    "legacy_runner_files_removed": 8,
    "validator_files_removed": 13,
    "historical_json_files_retained": 31
  }
}
```

The active subtotal fell 65.4%. The generic runner is below 3,450 lines, CAE is
below 4,200, their combined 5,946 lines are below 7,650, every module is below 700,
and every ordinary function is at most 100 lines. AST checks found no sibling
private imports and no duplicated top-level function body of 20 or more lines.

## Verification boundary

Source-checkout benchmark tests passed 73/73 using a fresh external pytest base and
no cache. The candidate wheel built and force-reinstalled successfully; import
resolved to `.venv/Lib/site-packages/yadof`. Installed-wheel surrogate/package
focused tests passed 61/61 and the complete suite passed 357/357. The no-write
`structural-full` plan succeeded and preflight passed 13/13. This change did not
create a run, execute a benchmark campaign or simulator, read a calibration/offline
locator, or access protected data.
