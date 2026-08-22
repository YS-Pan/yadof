# File blueprint: src/yadof/optimize/strategy.py

## Intent

- Define backend-neutral population, history, generation-context, result, and one
  complete strategy invocation contract.
- Fresh-load the sole complete composition from snapshotted
  `submit/optimization.py:build_optimization()`.

## Functionalities

- Validate the structural strategy protocol without training or evaluation.
- Build deterministic JSON semantic identity/signature from selected component
  identity plus parameter/objective names.
- Adapt current session history and provide the one common real-evaluation handoff.

## Invariants

- No concrete pymoo or Torch type crosses this boundary.
- Workspace strategy source is fresh and isolated; package config/registries never
  select another complete method.
- Surrogate predictions cannot become accepted results without real evaluation.
