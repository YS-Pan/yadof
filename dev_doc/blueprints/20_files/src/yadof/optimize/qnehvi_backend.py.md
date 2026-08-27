# File blueprint: src/yadof/optimize/qnehvi_backend.py

## Intent

- Provide the lightweight experimental Gate 2 call boundary for discrete
  sample-backed qLogNEHVI scoring without exposing a complete strategy.

## Functionalities

- Define the compact immutable result containing candidate-index batches, log
  acquisition values, and JSON-safe diagnostics.
- Accept fixed real baseline rows/costs plus already projected
  `JointObjectiveSamples` and explicit q batches.
- Lazily load the private BoTorch implementation and translate missing optional
  numerical dependencies into an actionable `yadof[qnehvi]` error.

## Invariants

- Parent `yadof.optimize` import stays independent of Torch and BoTorch.
- The result retains no posterior rawData or second history representation.
- This file does not generate candidates, run a generation, select a fallback,
  evaluate real work, or record evidence.
