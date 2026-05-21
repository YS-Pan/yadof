# 2026-05-20 10:41 - NSGA-III Surrogate Selection

## Context
- The active toDo handoff described a surrogate-assisted run that collapsed toward one objective tradeoff branch.
- The optimizer still used pymoo NSGA-II for multi-objective survival, and surrogate alpha selection compared predicted candidates position-by-position.
- Surrogate training checkpoints reported zero historical error because the audit path substituted true costs for predicted costs.

## Change
- Replaced the multi-objective pymoo path with NSGA-III and Das-Dennis reference directions, keeping GA only for single-objective problems.
- Added diagnostics for requested population size, reference-direction method, partition count, and reference-direction count.
- Changed surrogate alpha and beta phases to pool predicted candidates and select with NSGA-III survival.
- Added `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` so a small real-evaluation quota bypasses surrogate selection.
- Changed surrogate historical error audit to calculate costs from model-predicted rawData without exact-neighbor snapping.
- Added per-objective relative/absolute historical error quantiles and used them with ensemble spread to calibrate prediction intervals.
- Added task-owned `job_template.api.get_rawdata_importance_weights()` for the default cost observation windows and passed those query weights into surrogate INR training.
- Updated tests and documentation for NSGA-III, pooled survival, exploration quota, error calibration, and rawData importance weights.

## Rationale
- NSGA-III reference directions preserve representatives across objective tradeoff directions better than pairwise surrogate tournaments.
- Exploration slots reduce the chance that a biased surrogate fully starves an under-sampled branch before real evaluations can correct it.
- Historical error and interval calibration must reflect model predictions, otherwise optimizer-side uncertainty is artificially overconfident.
- Objective-relevant rawData windows should receive additional training attention without violating the full-field rawData-first surrogate contract.

## Impact
- Multi-objective optimizer diagnostics now report `pymoo.NSGA3` instead of `pymoo.NSGA2`.
- Surrogate checkpoints include historical relative-error p50/p90/p95 and absolute-error p90 fields.
- The default job template now exposes rawData importance weights for summary, curve-band, and surface-center objective windows.
- Documentation current views and blueprints now describe NSGA-III, exploration quota, calibrated intervals, and rawData importance weights.

## Follow-Up
- Tune `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION`, `SURROGATE_RAWDATA_IMPORTANCE_BOOST`, and interval floors on a real long-running campaign.
- If future task templates have different cost semantics, implement their own `get_rawdata_importance_weights()` hook or let surrogate training fall back to uniform weights.
