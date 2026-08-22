# File blueprint: src/yadof/optimize/state.py

## Intent

- Publish/read the one active semantic strategy pointer while retaining every
  inactive strategy/component artifact.

## Functionalities

- Derive `strategy-<signature-prefix>` from a validated SHA-256 signature.
- Atomically write `.yadof/optimization/active.json` with semantic identity and a
  separate optimization source hash.

## Invariants

- The pointer selects one active strategy but never deletes, migrates, or reads
  legacy component artifacts.
- Source hash inequality alone does not change semantic state compatibility or
  invalidate recorded real evidence.
