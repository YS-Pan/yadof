# File blueprint: backend/checkpoints.py

## Intent

Own checkpoint discovery, compatibility validation, artifact loading, device
selection, and both interactive and audit inference.

## Functionalities

- Parse only current-format `generation_*.json` descriptors below the active
  strategy's declared run/component namespace whose explicit
  method/policy/semantic identity is valid and whose unique namespace manifest is
  identical.
- Resolve namespace/artifact/model paths below the declared run/component namespace
  without legacy filename fallbacks or path traversal.
- Validate the semantic state signature against the checkpoint artifact's persisted
  train config/runtime version, plus current parameter normalization compatibility,
  rawData item count, modeled-slot shapes, scaler width, query table, and field count.
- Select the newest committed publication per generation within the active
  strategy/component scope, so an older compatible INR hyperparameter publication
  remains auditable without mixing retained inactive strategies.
- Load the conditional-INR ensemble through installed yadof.
- Predict member flat arrays, reconstruct mean/member rawData, and calculate current
  costs.
- Query a modeled slot at arbitrary physical coordinates and build mean/member
  `PlotData`; interpolate a constant unmodeled field directly from its template.
- Batch audit rows and reduce rawData errors per item.
- Report progress and cooperate with cancellation.
- Increase CUDA sample batching and recover from OOM by halving toward the
  configured baseline.

## I/O Format

`CheckpointPredictor.predict()` returns mean samples, cost rows, and optional member
sample batches. `predict_plot()` returns one mean plot plus member plots for a
`PlotRequest`. `predict_audit_rows()` returns cost rows plus four arrays shaped
`[sample, rawData item]`: relative/absolute sums and counts.

## Non-Obvious Techniques

- The checkpoint schema's `modeled_slots` determines which flattened values are
  predicted and compared.
- Ensemble mean is taken in flat scaled-output space after inverse scaling, then
  reconstructed through the checkpoint schema.
- Off-grid plot queries reuse the loaded model/schema/scaler but never replace the
  full-grid `predict()` path.
- Absolute and relative errors are reduced before rawData reconstruction is
  discarded, keeping audit memory small.
- Out-of-memory recovery must not shrink below the model's configured evaluation
  sample batch.

## Mutability Profile

Checkpoint format/method/policy changes require an explicit coordinated reader
change; they are not guessed. Parameter/schema compatibility, current-cost
calculation, per-item reduction, cancellation checks, and device fallback behavior
should remain explicit.
