# 2026-08-29 19:56 - Modularize Hierarchical CAE Frequency Filtering

## Context

- Hierarchical CAE's optional training-data assessment lived in the parent
  `surrogate/quality.py` module even though its only runtime consumer was the
  experimental hierarchical CAE and its calibration/viewer support.
- The fallback judges field morphology using spectral high-frequency energy,
  second differences, and derivative reversals. Calling the mechanism merely
  `quality` was too broad: any future filter will encode some notion of quality,
  so that name did not identify this implementation or leave a clear namespace for
  other filter types.
- `hierarchical_cae()` also lacked one explicit mode selector separating default
  ordinary training from opt-in filtering.

## Change

- Moved the implementation into
  `surrogate/hierarchical_cae/data_filtering/frequency.py` and added a small local
  `modes.py` dispatcher, mode-neutral `types.py`, and lightweight package exports.
- Added `hierarchical_cae(data_filter_mode=...)`. The default `none` mode produces
  uniform field/shared weights and no residual labels. The existing mechanism is
  selected as `frequency` and requires a versioned `frequency_filter` represented
  by `FrequencyFilter` and `FrequencyFilterRule`.
- Renamed generic training plumbing to data-filter terminology
  (`DataFilterAssessment`, `filter_weighted_loss`, and
  `shared_filter_isolation`) so future implementations do not inherit a
  frequency-specific or overly broad quality name.
- Rejected unknown modes, a frequency filter supplied while `none` is active, and
  `frequency` without a filter. There is no implicit mode inference or legacy
  `quality-regime` alias.
- Stored the selected mode and frequency-filter declaration in component semantic
  identity, training history, state signatures, and checkpoint manifests. The
  viewer validates the same payload.
- Updated focused tests, package-content assertions, architecture, blueprints,
  terminology, the active successor handoff, and user workflow guidance.

## Rationale

- `frequency` names the actual current classification signal and reserves sibling
  names below `data_filtering/` for future mechanisms.
- Component-local dispatch keeps filtering out of central campaign configuration
  and unrelated surrogate modules.
- The filter changes only a derived training view. It never deletes designs,
  selects a physical frequency-axis band, smooths source curves, filters by cost,
  or rewrites recorded rawData.

## Impact

- Callers that intentionally enable the existing mechanism now use
  `data_filter_mode="frequency"` and `frequency_filter=FrequencyFilter(...)`.
  Callers that omit filtering keep the default no-filter behavior.
- The former public `RawDataQualityPolicy`/`ShapeQualityRule` names, the
  `quality_policy` keyword, the `quality-regime` mode, and the direct
  `yadof.surrogate.quality` implementation path are removed without aliases.
- Because data-filter identity and train-config field names changed, checkpoints
  created with the former experimental quality-named payload are retained on disk
  but are incompatible and will not be activated as current state.
- Hierarchical CAE remains experimental/performance-not-accepted, and no simulator,
  benchmark campaign, calibration result, or release gate changes.

## Follow-Up

- A future filtering method should add one descriptively named implementation
  below `hierarchical_cae/data_filtering/`, extend explicit local mode validation
  and semantic identity, and add focused neutral tests. It must not create an
  ambient config fallback or mutate real evidence.
