# File blueprint: src/yadof/optimize/posterior_assisted.py

## Intent

- Implement an independent posterior-assisted generation-local selector while
  leaving GPSAF, its private phases/records, and real-search semantics unchanged.
- Retain the 0.4.x complete-strategy runner only as a closed cutover adapter.

## Functionalities

- Bind search, surrogate/posterior/readiness, acquisition, objective names, pool,
  draw/chunk, applicability, and exploration controls into semantic identity.
- Accept caller-owned `SurrogateTrainingData` for typed deterministic components
  and pass it into readiness, state, and sampler creation.
- Reuse `prepare_search()`/`search_candidates()` for the candidate pool and the
  shared `full_real_search()` for fallback, build a unique fixed real nondominated
  baseline, and enforce freshness plus typed readiness.
- Reserve an explicit real exploration quota; a calibrated applicability gate
  excludes below-threshold exploitation and audits low/boundary exploration.
- Create one persistent schema-bearing sampler, stream current-cost projection by
  chunks, select qNEHVI exploitation, and return the combined unique population as
  `PosteriorGenerationSelection` for program-owned real evaluation.

## Failure and invariants

- Static/runtime scientific blockers, missing baseline/state, projection/backend
  failure, or configured soft support failure use a complete real-search fallback.
- Configured support rejection propagates. Evaluation/finalization/recording are
  absent from `select_generation()`; the workspace program owns them. The legacy
  wrapper keeps them outside the selection catch, so recording failure aborts.
- Predicted rawData/costs never enter history and are never retained in metadata.
  Explicit training is controlled independently by the workspace program after it
  starts real evaluation.
- `JointObjectiveSamples` never becomes deterministic `PredictedCostRows`; qNEHVI
  support/configuration hard stops and common evaluator/recorder failures stay
  outside soft selection catches.
