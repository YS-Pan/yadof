# File blueprint: src/yadof/optimize/components.py

## Intent

- Expose the established pymoo GA/NSGA-III and objective-count search components,
  plus immutable GPSAF settings. Posterior-assisted and qNEHVI components live
  in their own narrow modules and are re-exported by `yadof.optimize`.

## Functionalities

- Validate objective compatibility and backend distribution availability.
- Report deterministic adapter/backend/version/algorithm/controlled-parameter
  identity.
- Lazy-load concrete pymoo implementation only when a selected operation runs.
- Expose `gpsaf_settings()` as the validated immutable settings surface for a
  program's generation-local selector, including the explicit `cluster` or
  `hypervolume` infill policy without changing the cluster default.
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
- Complete generation orchestration is absent; workspace programs hand the shared
  full-real primitive's population to the one common real evaluator.
