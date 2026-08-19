# 2026-08-19 15:52 - Revise Surrogate And Optimize Plans

## Context

- A fresh-context review identified avoidable churn between the modular-method plan
  and the later surrogate-simplification plan, plus ambiguity between replacing the
  complete optimizer and replacing only GPSAF's internal search algorithm.
- The current global query pool can under-sample small rawData fields, current
  training-set historical error and ensemble spread affect GPSAF noise decisions,
  and current checkpoint publication is not atomic.
- The user clarified that new optimizations may discard all old history/checkpoints,
  one workspace uses one method combination, ensemble/bootstrap/spread remain, and
  real benchmark tuning will follow after a clean baseline exists.

## Change

- Reversed the execution order: simplify the current surrogate first, then move the
  simplified implementation into method subpackages.
- Replaced global scalar-uniform query sampling with field/slot-balanced sampling
  and seeded cyclic coordinate coverage, with per-slot macro loss.
- Kept the deep ensemble, real-row bootstrap, and member spread output, while
  planning to remove spread and in-sample fit error from GPSAF candidate decisions
  until future out-of-sample benchmark calibration.
- Made the checkpoint plan fresh-only, method-namespaced, explicitly versioned by
  responsibility, and truly atomic; removed all legacy compatibility requirements.
- Split optimizer extensibility into a complete optimizer-method selector and a
  GPSAF-internal search-backend selector, so a future method may replace GPSAF or
  only replace pymoo GA/NSGA-III with a backend such as particle swarm.
- Removed same-workspace multi-method coexistence and narrowed speculative registry,
  capability, lifecycle, and file-layout requirements.
- Clarified that surrogate metrics are diagnostic during this cleanup; fast real
  problems such as `20260807 saw` are deferred to later benchmark-driven tuning.

## Impact

- No package code, runtime behavior, public API, checkpoint, history, or workspace
  file changed.
- Future work is tracked by, in order:
  1. `dev_doc/toDo/20260819_144148_simplify-surrogate-real-only-training.md`;
  2. `dev_doc/toDo/20260818_173629_modular-surrogate-optimize-methods.md`.

## Follow-Up

- Execute each manual toDo only when explicitly requested. Complete and archive the
  simplification toDo before starting the modularization toDo.
