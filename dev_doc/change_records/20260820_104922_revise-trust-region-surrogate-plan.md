# 2026-08-20 10:49 - Revise Trust-Region Surrogate Plan

## Context

- The long-term trust-region surrogate-gradient toDo predated the current
  rawData-first conditional-INR ensemble, GPSAF flow, generation task snapshots,
  mixed parameter representation, and the two staged surrogate simplification and
  modularization plans.
- Its generic recommendation to use ensemble uncertainty or historical surrogate
  error for trust conflicted with the newer decision to remove uncalibrated member
  spread and in-sample fit error from GPSAF candidate decisions.
- Source/caller review also showed that the live alpha/beta selection already uses
  mean predicted costs only. Noise/probabilistic-knockout helpers have no live
  caller, while historical error is fetched and passed through an unused argument;
  the newer plan and current module blueprints incorrectly described those signals
  as actively changing selection.
- The current production cost path reconstructs rawData and calls arbitrary
  task-owned Python/NumPy cost code, so a differentiable Torch model does not by
  itself provide an end-to-end objective gradient.

## Change

- Revised the old manual toDo to depend on the real-only surrogate simplification
  and modular surrogate/optimizer tasks in their established order.
- Reframed the work as rawData-surrogate local refinement with real validation and
  required benchmarked out-of-sample trust evidence.
- Added explicit implementation decisions for the derivative contract, optimizer
  ownership, mixed-parameter behavior, and benchmark/calibration gate.
- Aligned the proposed workflow with generation snapshots, current-cost
  reinterpretation, the common evaluator/finalizer, campaign-session history,
  method provenance, Pareto diversity, and bounded exploration.
- Corrected the real-only simplification toDo and current surrogate/optimize
  blueprints to distinguish dead trust/noise surfaces from the live mean-cost
  selection path. The planned removal and selection-invariance tests remain.

## Rationale

- The long-term direction remains useful, but implementing the old wording would
  either restore trust signals that the newer plan deliberately removes or imply a
  gradient through a non-differentiable task-cost boundary.
- Keeping the unresolved high-impact choices explicit avoids prematurely expanding
  every surrogate method or task cost into a gradient API and avoids misclassifying
  trust-region model management as a GPSAF evolutionary search backend.

## Impact

- No package code, runtime behavior, public API, checkpoint, history, architecture,
  terminology, or user workflow changed.
- The active manual trust-region toDo now describes the current prerequisite and
  design boundaries rather than the May 2026 module assumptions.
- The first-stage surrogate toDo and two current module blueprints now accurately
  describe the existing decision path; only future-work and current-view
  documentation changed.

## Follow-Up

- Complete the real-only training task and modular-method task before triggering
  the revised trust-region toDo.
- Before implementation, the user must select the derivative strategy, optimizer
  ownership, mixed-parameter policy, and real benchmark/calibration gate described
  in that toDo.
