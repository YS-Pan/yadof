# Module blueprint: surrogate

## Responsibility

`yadof.surrogate` models workspace rawData as a function of normalized variables and
rawData query coordinates. It trains a conditional implicit-neural-representation
ensemble, reconstructs predicted rawData, calculates current costs through
`job_template`, exposes per-objective member min/max intervals, audits historical
error, and publishes recoverable checkpoints/metadata.

## Training data and model

Training bundles come from the active campaign session when one exists, so finalized
segments and accepted unpublished current rows share one validated view. Outside a
campaign they come from tolerant public recorded-data queries. RawData fields are flattened
into query-aligned numeric slots with schema/axis identity; target scaling handles
constant or near-constant fields. Task-owned importance weights do not add or remove
rawData: they emphasize objective-relevant positions already present in the modeled
query table. They weight full-query loss or, when large fields use stochastic query
minibatches, determine query-sampling probabilities without weighting the sampled
loss a second time. A positive baseline weight retains attention outside the
emphasized window. Public prediction reconstructs the full compatible field.

The conditional decoder may also be queried at arbitrary physical coordinates for
one modeled rawData slot. Stored coordinate values use exactly the checkpoint's
original normalized coordinates and scaler entries. Between stored values, only
the per-coordinate target mean/scale is linearly interpolated before inverse
scaling; the decoder itself is evaluated at the requested coordinate. Values
outside the stored axis range are decoder extrapolation, with endpoint-clamped
scaler values. This query path is additive: training, checkpoint serialization,
full-grid reconstruction, optimizer prediction, and audit behavior remain
unchanged.

Ensemble members may bootstrap samples and use configured latent, embedding,
Fourier-feature, hidden-layer, batch, optimizer, non-finite, and mixup policies.
Mixup is a configurable low-weight interpolation regularizer rather than a second
source of truth: real evaluated rawData remains the dominant training loss, and a
workspace may set its weight to zero for sharply nonlinear physical responses.
Member spread becomes uncertainty input for optimizer screening; it is not durable
truth.

## Scheduling and recovery

Runtime state and training schedules are keyed by effective workspace/checkpoint
paths. At most one background training task runs per workspace. Real jobs are
submitted first, then training may use the waiting interval; maximum generation lag
bounds stale models. An asynchronous trainer receives an owned task snapshot and
training bundle rather than reopening mutable task files. Clearing one workspace
waits/resets only that workspace.

Checkpoints contain model artifacts, auxiliary arrays, parameter/rawData signatures,
generation identity, config summary, and audit metadata. Recovery requires
compatible current parameters/rawData schema. Current `calc_cost.py` is reapplied to
predicted rawData after recovery, so cost policy is never frozen in a checkpoint.

## Invariants

- No direct authoritative `variables -> cost` model path.
- No checkpoint or scheduler collision across workspaces.
- Training never needs to scan history per candidate and never depends on a segment
  being published before a current accepted row becomes useful.
- Non-finite/corrupt history is diagnosed and bounded by policy.
- Prediction output passes the same rawData/cost interpretation used for real data.
- Full-grid prediction never routes through optional off-grid interpolation.
