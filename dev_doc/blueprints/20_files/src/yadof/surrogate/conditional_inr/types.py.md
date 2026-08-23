# File blueprint: src/yadof/surrogate/conditional_inr/types.py

## Intent
- Hold shared surrogate type aliases and dataclasses so runtime, scheduler, and checkpoint helpers do not duplicate structural definitions.

## Functionalities
- Define population/rawData aliases.
- Define `TrainingData`, `RawArraySlot`, `RawDataSchema`, `TargetScaler`, and `SurrogateState`.

## I/O Format
- Dataclasses are in-memory structures. They are not persisted directly; checkpoint and metadata helpers serialize selected fields.

## Non-Obvious Techniques
- `SurrogateState` holds active/namespace manifest paths, artifact/model paths,
  active strategy plus semantic state/run/component identity, schema/scaler/model, train config, and
  compact training history. It does not hold duplicated training evidence or
  historical trust/error surfaces.

## Mutability Profile
- Add fields only when multiple surrogate files need them or when state persistence/diagnostics require them.
