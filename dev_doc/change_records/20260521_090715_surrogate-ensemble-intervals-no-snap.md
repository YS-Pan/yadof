# 2026-05-21 09:07 - Surrogate Ensemble Intervals And No Snap

## Context
- The surrogate prediction interval had accumulated several calibration sources: ensemble spread, historical relative-error p90, historical absolute-error p90, and fixed floors.
- The user wanted interval output to directly reflect the range of deep-ensemble member predictions, without adding a delta around the mean prediction.
- The user also wanted exact-neighbor snapping removed and not reintroduced unless explicitly requested.

## Change
- Changed `surrogate.runtime.predict_population()` intervals to the per-objective minimum and maximum costs across deep-ensemble members.
- Removed exact-neighbor snapping code and the `SURROGATE_EXACT_NEIGHBOR_RADIUS` configuration.
- Removed obsolete interval floor configuration that is no longer used by the simplified interval contract.
- Made local evaluation reload `project/config.py` when reading `LOCAL_EVALUATION_MAX_WORKERS`, allowing worker-count edits to take effect on the next generation/evaluation call.
- Updated tests and current documentation to describe ensemble min/max intervals and the no-snap contract.

## Rationale
- Ensemble min/max intervals are easier to interpret and do not imply symmetry around the mean prediction.
- Removing snap keeps historical prediction audits and optimizer-facing predictions on the same model-prediction basis.
- Re-reading the local worker count at evaluation boundaries gives users coarse runtime control without changing an in-flight generation.

## Impact
- `predict_population()` still returns `(costs, ((lower, upper), ...))`, but `lower` and `upper` now come only from member-level predicted costs.
- Historical error audit fields remain available for diagnostics, but they no longer calibrate intervals.
- Local worker-count changes in `project/config.py` are picked up at the next local `evaluate_population()` call when no explicit `local_max_workers` override or environment variable is used.

## Follow-Up
- If a future task needs snap-like behavior, implement it only after a direct user request and document why it is appropriate for that task.
