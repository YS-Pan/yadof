# 2026-08-31 15:38 - Migrate Retained Optimization Capabilities

## Context

- Stage 6 introduced an explicit workspace optimization program while retaining a
  closed compatibility path. Stage 7 had to move every retained deterministic,
  posterior, example, starter, and benchmark consumer onto explicit data and
  lifecycle boundaries before the final cutover.
- The first and only authorized smoke run exposed a duplicate PCA/SVD training
  side effect in selection freshness. The measured acceptance therefore had to
  prove the corrected read-only selection and lagged-checkpoint behavior.

## Change

- Added typed deterministic-surrogate training, prediction, scheduler, latest-state,
  and pure freshness contracts. Conditional-INR and hierarchical CAE now consume
  explicit `SurrogateTrainingData`; posterior adapters receive explicit schema data.
- Added pure generation-local GPSAF and posterior selections plus explicit
  evaluation/training lifecycle helpers. Legacy orchestration remains only as a
  closed Stage 8 deletion surface.
- Preserved exact PCA/SVD recovery and added verified, read-only recovery of the
  exact lagged evidence subset. Canonical JSON comparison preserves tuple/list
  settings identity without weakening digest or artifact checks.
- Migrated the starter, HFSS example, and all three benchmark baselines to visible
  selection, evaluation-handle, training, and commit order. Updated tests, user
  documentation, architecture, terminology, blueprints, and active scientific
  handoffs to describe the explicit boundary.

## Rationale

- A selection operation must remain referentially transparent with respect to
  evaluation, fitting, checkpoint writes, and generation commit. Recovery of an
  already committed lagged model satisfies that rule while preserving the Stage 6
  one-generation training/evaluation overlap.
- Keeping blocked posterior readiness and existing `gamma` identity semantics
  avoids manufacturing scientific acceptance while allowing the orchestration
  boundary to migrate independently.

## Impact

- Corrected installed-wheel acceptance passed: final focused tests `48/48`, full
  yadof tests `448/448`, and benchmark tests `21/21`.
- The exact-once smoke completed `40/40` finite evaluations and exposed the
  duplicate-training defect; it was intentionally not rerun. The corrected-wheel
  measured run completed `2000/2000` finite evaluations with zero issues and
  exactly 19 unique lag-one training/checkpoint events for generations 1--19.
- No real simulator, HTCondor execution, posterior eligibility claim, acquisition
  protocol, CAE scientific redesign, noise model, or trust-region work was added.

## Follow-Up

- Stage 8 must delete the now-closed legacy strategy/campaign/materializer/callback
  and `build_optimization()` compatibility surfaces, finish the 0.5.0 cutover, and
  rerun release acceptance.
