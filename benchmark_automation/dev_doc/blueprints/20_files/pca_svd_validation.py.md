# Blueprint: `pca_svd_validation.py`

## Contract

Remain a thin v11 CLI over `experiment_runtime.linear_subspace`. `plan` reads the
sealed preregistration without fitting or writing; `preflight` requires an explicit
partition; `run` requires `--allow-measured-run` while the manifest independently
supplies execution authority and sealed thresholds. Only an authorized run may
write `--output`.
