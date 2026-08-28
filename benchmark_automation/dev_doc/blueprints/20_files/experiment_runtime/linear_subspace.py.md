# Blueprint: `experiment_runtime/linear_subspace.py`

## Contract

Validate an absolute, design-disjoint SAW/Chrono/test-com partition with no test
locator. Preflight is schema-only and never opens recorded evidence or fits a
model. An authorized run reads only public recorded-data APIs, executes the fixed
PCA/SVD oracle and ridge arms, reports per-field macro/current-cost/resource
metrics plus deployable-minus-oracle gaps, and never permits formal or posterior
claims.
