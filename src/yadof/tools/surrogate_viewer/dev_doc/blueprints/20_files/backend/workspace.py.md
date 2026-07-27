# File blueprint: backend/workspace.py

## Intent

Present one explicit yadof workspace as a read-only viewer facade and orchestrate
the complete cross-generation audit.

## Functionalities

- Load checkpoints, task parameter/objective definitions, completed records, and a
  rawData template.
- Normalize record metadata into sorted `RealResult` values.
- Retrieve true rawData and calculate current true costs.
- Cache one interactive `CheckpointPredictor`.
- Sample each generation independently.
- Bulk-load sampled rawData and calculate true costs once.
- For every checkpoint, flatten true samples, run inference, aggregate cost and
  per-rawData error arrays, report progress, and free checkpoint resources.
- Publish a `CrossGenerationErrorAudit` only after full completion.

## I/O Format

`predict_one()` returns `PredictionResult`.

`calculate_error_audit()` accepts fraction, seed, cancellation event, progress
callback, outer batch size, and CUDA sample batch. It returns arrays shaped:

```text
[optimization generation, checkpoint generation, objective]
[optimization generation, checkpoint generation, rawData item]
```

## Non-Obvious Techniques

- Sampling uses `ceil(generation size × fraction)` with a minimum of one.
- The same ordered sampled rows feed every checkpoint in an audit.
- True flat matrices are cached by a schema key only for the current audit.
- Relative error uses the workspace's `SURROGATE_RELATIVE_ERROR_EPS`.
- Progress total is sampled rows multiplied by checkpoint count.
- Predictor deletion and optional `torch.cuda.empty_cache()` happen after each
  checkpoint column.

## Mutability Profile

Sampling UI defaults and batching may change. Stable contracts are explicit
workspace scope, current-cost interpretation, identical rows across checkpoints,
axis ordering, full-completion publication, and no writes.
