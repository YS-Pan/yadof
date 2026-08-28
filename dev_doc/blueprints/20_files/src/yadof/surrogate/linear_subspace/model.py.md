# Blueprint: `surrogate/linear_subspace/model.py`

## Contract

Concatenate per-field coefficients only after independent basis fitting and solve
one stable multi-output ridge system without scikit-learn. The optional intercept
is unpenalized. Prediction accepts finite normalized `[0, 1]` parameters, rebuilds
complete transient structured rawData, rounds/clamps integer fields, and never
calculates or records an authoritative direct parameter-to-cost result.
