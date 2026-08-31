# File blueprint: src/yadof/optimize/gpsaf/assistance.py

## Intent
- Select one GPSAF generation from injected search and a typed rawData-surrogate
  component without owning real evaluation, training timing, recording, or commit.

## Functionalities
- Receive common generation context/history/problem shape and invoke shared search
  primitives with the injected search settings snapshot.
- Require a runtime-checkable `DeterministicSurrogateComponent` and caller-owned
  `SurrogateTrainingData`; thread that exact value through a pure state-age check,
  readiness, and typed prediction.
- Use the latest compatible trained state only within the configured lag. Missing
  or stale state falls back to real selection without starting or waiting for fit.
- On any soft derived selection/materialization/prediction failure, discard the
  partial selection and run one fresh complete full-real primitive; failure of that
  real path remains explicit.
- Return `GPSAFGenerationSelection` with population/source/surrogate-use/diagnostics
  only; it cannot evaluate or commit.
- Expose explicit start/finish training helpers so the workspace program can start
  evaluation first, start training on prior immutable evidence, and close both
  lifecycles before commit.

## I/O Format
- The selector returns `GPSAFGenerationSelection`; the workspace program converts
  real evaluation output into `OptimizationResult` at commit.

## Non-Obvious Techniques
- Selection has no training/evaluation side effect. The explicit program controls
  the truthful `start evaluation -> start training -> wait/close` ordering. Lag
  policy is a read-only selection gate, not a blocking scheduler call.

## Mutability Profile
- Keep only irreducible alpha/beta/exploration and staggered-component coordination.
- Alpha, beta, gamma, and exploration arrive as one immutable factory-owned GPSAF
  snapshot; no phase reads ambient algorithm config. `gamma` remains validated,
  identified, and diagnosed but does not enter selection mathematics.
  Pymoo owns algorithms/operators/survival through `primitives.py`; common
  evaluation/history/types stay in `strategy.py`.
