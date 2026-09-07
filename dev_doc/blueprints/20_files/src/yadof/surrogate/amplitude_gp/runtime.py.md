# Blueprint: surrogate/amplitude_gp/runtime.py

## Contract

Expose explicit fit/start-fit, exact or compatible lagged recover, and typed
snapshot-bound prediction. No hidden history query is permitted. Default
materialization sorts successful evidence by generation/population/row ID;
explicit caller row order remains intact. Low-level fit validates minimum sample
count, unique IDs, named parameters and snapshot ownership, projects only owned
selected rawData for current-cost priorities, and delegates numerical training.

## Identity and publication

Bind exact content, schema, normalized parameter definitions/order, all settings,
NumPy/SciPy/sklearn/threadpoolctl versions, active strategy and training-priority
interpretation. Keep content separate from provenance. Use generation-owned
`TrainingHandle` and snapshot cleanup; cancellation cannot publish an incomplete
state. Publish independent checkpoint metadata and one training event, then cache
by workspace/strategy/settings without replacing a newer generation with an older
one.

## Recovery and prediction

Normalize source identity across campaign and standalone snapshot forms by
hashing the complete submit plus parameter source set, including frozen program
hashes. Preserve the actual snapshot interpretation on prediction DTOs.
For persisted committed rows whose normalized coordinates changed only through
the physical-coordinate round trip, require unchanged row/evidence IDs, masks,
statuses and physical metadata; exact fitted-X denormalization and exact incoming-X
normalization must both match that record. Only then restore the saved fitted X
and require the original full content digest. No epsilon tolerance or reconciliation
of derived rows is allowed. Arbitrary coordinate/rawData/record edits fail closed.

Recover only namespace manifests whose exact old ordered rows can be reconstructed
from the explicit supplied data. Exact recovery requires the full fitted content;
selection may use compatible unchanged prefixes. Check all identity dimensions,
shapes and hashes, and skip corrupt or stale publications without retraining.
Prediction returns genuine complete rawData and current-snapshot projected costs
with zero-width intervals. Parameter drift rejects prediction. A changed cost
snapshot can reproject an explicitly retained raw model, but selection reuse must
refit because the GP row subset depends on the cost interpretation. Invalid
predictions have no rawData, all +inf costs/intervals and false validity.
Prediction/recovery never record observations or advance formal history.
