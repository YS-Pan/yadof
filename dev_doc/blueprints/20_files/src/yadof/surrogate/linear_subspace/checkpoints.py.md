# Blueprint: `surrogate/linear_subspace/checkpoints.py`

## Contract

Publish one no-pickle NPZ artifact and JSON manifest atomically below the active
strategy's `components/pca-svd` namespace. State identity binds parameter
definitions, exact rawData template, semantic training-data content digest, all
component settings, and NumPy/Torch versions. Ordered row/evidence identities,
statuses, lineage, and optional transform intent are stored under a separate
provenance digest and cannot replace or invalidate identical mathematics.
Recovery cold-fits legacy manifests without the exact-content fields and verifies
paths, identities, dimensions, and artifact SHA-256 before constructing a model.
