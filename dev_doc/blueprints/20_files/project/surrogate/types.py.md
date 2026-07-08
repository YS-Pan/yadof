# File blueprint: project/surrogate/types.py

## Intent
- Hold shared surrogate type aliases and dataclasses so runtime, scheduler, and checkpoint helpers do not duplicate structural definitions.

## Functionalities
- Define population/rawData aliases.
- Define `TrainingData`, `RawArraySlot`, `RawDataSchema`, `TargetScaler`, and `SurrogateState`.

## I/O Format
- Dataclasses are in-memory structures. They are not persisted directly; checkpoint and metadata helpers serialize selected fields.

## Non-Obvious Techniques
- `SurrogateState` intentionally includes both model artifacts and historical audit summaries because prediction and diagnostics use the same latest trained state.

## Mutability Profile
- Add fields only when multiple surrogate files need them or when state persistence/diagnostics require them.
