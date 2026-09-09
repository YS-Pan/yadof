# Blueprint: surrogate/amplitude_gp/model.py

## Contract

Own all field-agnostic numerical learning, with no workspace or recorder IO.
Consume explicit ordered selected rows, finite current-cost priorities and frozen
settings. Preserve the successful development mathematics: full-prefix codecs,
bounded stable cost-elite plus farthest-design-coverage GP rows, asinh minimum,
log positive span, unit-range shape, randomized PCA, and shared-kernel shape GP.
Use one bounded L-BFGS-B start per GP and one numerical thread.

Allocate one C-contiguous float64 target per field and fill it row by row directly
from immutable samples. `fit_field()` consumes that private buffer: subtract/divide
in place, then let randomized PCA center it with `copy=False`. Constant-span rows
remain zero. Release the target and its last row view before allocating the next
field in each worker. Optional bounded `field_workers` runs independent fields in
threads under one enclosing numerical-thread scope, sharing only immutable inputs.
Store outputs in schema order. Failure signals peer cancellation and joins every
worker before returning; no partial model is published. Parallel workers use
normal process warnings instead of racing process-global warning capture contexts;
serial fits retain field warning lists. Prediction normalization remains non-mutating. Never mutate shared input
samples, reduce precision, or truncate the full-prefix codec to save memory.

## Prediction and state

Retain GP kernel, training X, solved alpha, normalization mean/std, and PCA
components/mean. These numeric sufficient statistics reproduce central sklearn
means and unwhitened inverse PCA without serializing estimators. Constant maps
return their target mean. Recenter/rescale decoded shape to restore learned
extrema, reconstruct every schema field including axes/static payload, and
count collapsed positive spans. Never borrow known responses. Nonfinite
transforms or values outside the target integer dtype range produce an invalid
sample; float cast overflow is also invalid.

## Lifecycle and evidence

Cooperatively check cancellation between fields, before/after maps and at every
optimizer objective evaluation. No fit produces a checkpoint here. Diagnostics
record selected GP row IDs, field transforms/kernels/warnings and timing.
Installed-model verification compares numerical predictions across the memory
optimization and covers multidimensional payloads, scalar and constant fields.
