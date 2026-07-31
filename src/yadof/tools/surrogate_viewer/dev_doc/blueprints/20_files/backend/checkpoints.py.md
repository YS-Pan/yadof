# File blueprint: backend/checkpoints.py

## Intent

Own checkpoint discovery, compatibility validation, artifact loading, device
selection, and both interactive and audit inference.

## Functionalities

- Parse usable `generation_*.json` descriptors.
- Resolve artifact/model filenames without accepting path traversal outside the
  checkpoint artifact directory.
- Validate current parameter names, rawData item count, modeled-slot shapes,
  scaler width, query table, and field count.
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

Artifact fields and model APIs may change with yadof. Parameter/schema
compatibility, current-cost calculation, per-item reduction, cancellation checks,
and device fallback behavior should remain explicit.
