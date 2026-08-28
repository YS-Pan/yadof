# Blueprint: `surrogate/linear_subspace/codec.py`

## Contract

Freeze the exact named rawData template from training evidence, reject incomplete,
complex, object, structured, or non-finite fields, and fit one basis per field.
PCA subtracts/adds the training coordinate mean; SVD uses a zero mean. Clamp rank
explicitly, canonicalize basis signs, preserve main shape/dtype and every non-main
template value, and lazy-import Torch only when a nonzero basis is fitted.

`fit_codec()`/`evaluate_oracle()` may encode known validation truth and return a
diagnostic-only result. `fit_deployable()` delegates to the ridge model and accepts
validation candidates only as normalized parameters after fitting.
