# Blueprint: `surrogate/linear_subspace/settings.py`

## Contract

Own the immutable, eagerly validated settings snapshot behind `pca_svd()`: centered
PCA versus uncentered SVD, per-field clamp policy, Torch low-rank solver, dtype,
seed/power iterations/device, and deterministic ridge/intercept values. Every
field is semantic identity; no ambient uppercase fallback or second settings path
is allowed.
