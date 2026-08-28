# Blueprint: `surrogate/linear_subspace/types.py`

## Contract

Define aligned named training data, per-field basis metadata, a codec without a
parameter predictor, the deployable ridge model, the diagnostic-only oracle result,
and workspace state paths/signatures. Oracle and deployable types must remain
non-interchangeable; no type claims posterior support.
