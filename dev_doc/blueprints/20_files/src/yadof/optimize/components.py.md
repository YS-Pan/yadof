# File blueprint: src/yadof/optimize/components.py

## Intent

- Expose the established pymoo GA/NSGA-III, objective-count dispatch, GPSAF, and
  real-search components with component-owned immutable settings. Posterior-assisted and qNEHVI components live
  in their own narrow modules and are re-exported by `yadof.optimize`.

## Functionalities

- Validate objective compatibility and backend distribution availability.
- Report deterministic adapter/backend/version/algorithm/controlled-parameter
  identity.
- Delegate real-only execution to the shared full-real primitive and lazy-load
  concrete pymoo/GPSAF implementation only when a selected strategy runs.
- Give each public factory an explicit keyword-only configuration surface. Construct
  and eagerly validate private frozen settings without accepting a settings object,
  unrestricted kwargs, or ambient algorithm config.
- Combine component payloads with core population/archive/freshness campaign policy
  while preserving deterministic strategy identity.

## Invariants

- Pymoo owns algorithms, population operators, ask/tell, reference-direction
  survival, mutation, and crossover. Yadof does not copy those numerical loops.
- NSGA-III-only fails below two objectives and never falls back to GA.
- No unrestricted kwargs, generic plugin graph, refinement role, or SciPy path.
- Runtime receives the selected search/GPSAF settings snapshot through narrow
  arguments; it never looks up removed uppercase algorithm names.
- RealSearchStrategy owns no private history/survivor/ask/refill loop; it hands the
  primitive's population to the one common real evaluator.
