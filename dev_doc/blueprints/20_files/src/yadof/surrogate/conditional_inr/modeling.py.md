# File blueprint: src/yadof/surrogate/conditional_inr/modeling.py

## Intent
- Own conditional-INR model construction, fitting, persistence, and batched
  member inference.

## Functionalities
- Build the configured conditional-INR ensemble.
- Train members from normalized variables and rawData query tables.
- Save and load member weights.
- Predict scaled modeled-slot values with configured batching and device handling.

## I/O Format
- Consumes `TrainingData`, query tables, train configuration, and normalized input
  rows.
- Returns model members, compact training history, or member prediction arrays.

## Non-Obvious Techniques
- Modeling owns tensors and accelerator details, while runtime owns rawData
  reconstruction, checkpoint publication, and task cost calculation.

## Mutability Profile
- Network and training internals may evolve when checkpoint compatibility is
  changed explicitly; task-owned evidence and cost semantics remain outside this
  file.
