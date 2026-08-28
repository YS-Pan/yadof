# File blueprint: src/yadof/optimize/qnehvi/acquisition.py

## Intent

- Expose the public `qnehvi()` family component without owning a generation or
  duplicating BoTorch hypervolume numerics.

## Functionalities

- Validate multi-objective shape, explicit batch/restart/reference/device controls,
  honest finite support policy, unique normalized candidate pools, and unsupported
  pending/outcome inputs.
- Score all singletons, expand the best configured starts greedily, and choose one
  deterministic batch; every value comes from `qnehvi.backend`.
- Return only selected indices, one log acquisition value, and bounded backend/
  support/time/memory diagnostics.

## Failure and invariants

- `fallback` support is a typed soft signal, `reject` is a typed hard stop, and
  incompatible source-support configuration is explicit.
- Importing the module never imports Torch or BoTorch. It contains no candidate
  generator, rawData projection, evaluator, recorder, or home-grown hypervolume.
