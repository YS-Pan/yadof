# Blueprint: `surrogate/linear_subspace/types.py`

## Contract

Define per-field basis metadata, a codec without a parameter predictor, the
deployable ridge model, the diagnostic-only oracle result, and workspace state
paths/content/provenance signatures. The component-neutral aligned training and
prediction values live in parent `surrogate/training.py`. Oracle and deployable
types must remain non-interchangeable; no type claims posterior support.
