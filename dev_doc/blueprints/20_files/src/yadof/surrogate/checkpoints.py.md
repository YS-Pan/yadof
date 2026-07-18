# File blueprint: src/yadof/surrogate/checkpoints.py

## Intent
- Own surrogate checkpoint and auxiliary artifact serialization.

## Functionalities
- Write generation JSON summaries.
- Write `model_aux.npz` with query tables, field ids, target scaling, training flat values, and query weights.
- Convert `RawDataSchema` and train config into JSON-safe summaries.

## I/O Format
- Checkpoint JSON is `generation_*.json`.
- Auxiliary artifact is `generation_*_conditional_inr/model_aux.npz`.

## Non-Obvious Techniques
- Member model weights are saved by `modeling.py`; this file writes the runtime-level summary and auxiliary arrays.
- Checkpoint summaries should describe rawData-first prediction and never store surrogate-predicted evaluation history as durable truth.

## Mutability Profile
- Payload fields may grow, but readers should treat checkpoint JSON as diagnostic/recovery metadata rather than the source of real evaluation results.
