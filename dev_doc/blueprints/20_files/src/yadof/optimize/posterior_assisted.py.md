# File blueprint: src/yadof/optimize/posterior_assisted.py

## Intent

- Implement the independent posterior-assisted complete strategy while leaving
  GPSAF, its private phases/records, and real-search semantics unchanged.

## Functionalities

- Bind search, surrogate/posterior/readiness, acquisition, objective names, pool,
  draw/chunk, applicability, and exploration controls into semantic identity.
- Reuse `prepare_search()`/`search_candidates()` for the candidate pool and the
  shared `full_real_search()` for fallback, build a unique fixed real nondominated
  baseline, and enforce freshness plus typed readiness.
- Reserve an explicit real exploration quota; a calibrated applicability gate
  excludes below-threshold exploitation and audits low/boundary exploration.
- Create one persistent schema-bearing sampler, stream current-cost projection by
  chunks, select qNEHVI exploitation, and hand the combined unique population to
  common real evaluation.

## Failure and invariants

- Static/runtime scientific blockers, missing baseline/state, projection/backend
  failure, or configured soft support failure use a complete real-search fallback.
- Configured support rejection propagates. Common evaluation/finalizer/recording
  happen outside the selection catch, so recording failure aborts normally.
- Predicted rawData/costs never enter history and are never retained in metadata.
  Training notification occurs only after real jobs are submitted.
- `JointObjectiveSamples` never becomes deterministic `PredictedCostRows`; qNEHVI
  support/configuration hard stops and common evaluator/recorder failures stay
  outside soft selection catches.
