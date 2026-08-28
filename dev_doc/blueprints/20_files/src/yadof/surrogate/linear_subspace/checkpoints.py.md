# Blueprint: `surrogate/linear_subspace/checkpoints.py`

## Contract

Publish one no-pickle NPZ artifact and JSON manifest atomically below the active
strategy's `components/pca-svd` namespace. State identity binds parameter
definitions, exact rawData template, recorded training-design contents and row
identities, all component settings, and NumPy/Torch versions. Recovery verifies
paths, identities, dimensions, and artifact SHA-256 before constructing a model.
