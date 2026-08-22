# File blueprint: src/yadof/optimize/components.py

## Intent

- Expose only the small production compositions currently required: pymoo GA,
  pymoo NSGA-III, objective-count dispatch, GPSAF with an injected rawData
  surrogate, and real search.

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
