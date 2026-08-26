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
- Normalize design inputs from `[0, 1]` to `[-1, 1]`, predict unbounded per-query
  standard scores through a near-zero-initialized linear output layer, and persist
  an explicit architecture version so old bounded-output weights cannot cross-load.
- Field-balanced query sampling uses one seeded permutation per field and advances
  a deterministic cursor across training steps, completing coordinate coverage
  before repeating a field's query positions.
- Every independently initialized member sees all retained real rows by default;
  bootstrap remains explicit opt-in because ensemble spread is diagnostic and does
  not justify discarding unique design support from the fitted mean. Requested
  bootstrap resampling is still deferred while the real sample count is below twice
  the input dimension.

## Mutability Profile
- Network and training internals may evolve when checkpoint compatibility is
  changed explicitly; task-owned evidence and cost semantics remain outside this
  file.
