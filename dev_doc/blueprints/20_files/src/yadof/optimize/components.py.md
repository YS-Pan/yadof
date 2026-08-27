# File blueprint: src/yadof/optimize/components.py

## Intent

- Retain the established pymoo GA/NSGA-III, objective-count dispatch, GPSAF, and
  real-search components unchanged. Posterior-assisted and qNEHVI components live
  in their own narrow modules and are re-exported by `yadof.optimize`.

## Functionalities

- Validate objective compatibility and backend distribution availability.
- Report deterministic adapter/backend/version/algorithm/controlled-parameter
  identity.
- Lazy-load concrete pymoo/GPSAF implementation only when a selected strategy runs.

## Invariants

- Pymoo owns algorithms, population operators, ask/tell, reference-direction
  survival, mutation, and crossover. Yadof does not copy those numerical loops.
- NSGA-III-only fails below two objectives and never falls back to GA.
- No unrestricted kwargs, generic plugin graph, refinement role, or SciPy path.
