# File blueprint: src/yadof/evaluate_manager/api.py

## Intent

- Compose public evaluation preparation, handle execution, backend dispatch, and
  the synchronous convenience API through one implementation.

## Functionalities

- `prepare_evaluation()` materializes an input iterable, applies batch-level config
  overrides, validates the selected mode/runtime, and returns an `EvaluationBatch`.
- `start_evaluation()` creates and starts an `EvaluationHandle`, cleaning a
  registered lease if thread startup fails.
- The handle-owned executor creates a private session/snapshot when needed, selects
  fast/local/distributed dispatch, builds bounded status diagnostics, and returns
  the finalized `EvaluationResult` before closing private scope.
- Each dispatch returns ordered finalized `JobResult` rows from the same
  `ResultFinalizationCoordinator`. The `EvaluationResult.costs` property supplies
  the synchronous cost tuple.
- Create durable per-candidate cancelled results for work skipped before prepare or
  run; retain preparation, execution, timeout, and recorder failure distinctions.

## Invariants

- `evaluate_population()` and `run_smoke_test()` are prepare/start/wait/close
  compositions, not alternate dispatch paths.
- Smoke is one candidate, one worker, and no timeout while still using the common
  handle/finalizer/session lifecycle.
- Evaluation batches and backend dispatch expose no submission callback; overlap
  is visible in caller-owned handle ordering.
- Objective width and population order are frozen before start and retained for
  every success, failure, timeout, or cancellation result.
