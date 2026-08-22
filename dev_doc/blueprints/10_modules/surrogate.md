# Module blueprint: surrogate

## Responsibility

`yadof.surrogate` models workspace rawData as a function of normalized variables and
rawData query coordinates. It trains a conditional implicit-neural-representation
ensemble, reconstructs predicted rawData, calculates current costs through
`job_template`, exposes per-objective member min/max spread diagnostics, and
publishes recoverable checkpoints/metadata. Its lightweight public factory is a
narrow rawData-surrogate component injected by workspace-owned GPSAF composition;
non-surrogate strategies do not load or create this state.

## Training data and model

Training bundles come from the active campaign session when one exists, so finalized
segments and accepted unpublished current rows share one validated view. Outside a
campaign they come from tolerant public recorded-data queries. RawData fields are flattened
into query-aligned numeric slots with schema/axis identity; target scaling handles
constant or near-constant fields. Training targets are only recorded real rows or
seeded bootstrap draws from them. Query minibatches are seeded, balanced across
active fields, and sampled without replacement inside each field. Pointwise Smooth
L1 is averaged within each field and then macro-averaged equally across fields.
Task-owned weights and synthetic target paths do not exist. Public prediction
reconstructs the full compatible field.
When the configured finite training schedule is too short to give every active field
the same number of appearances under a smaller query budget, the effective epoch
count is extended only far enough to complete one deterministic rotation cycle.

The conditional decoder may also be queried at arbitrary physical coordinates for
one modeled rawData slot. Stored coordinate values use exactly the checkpoint's
original normalized coordinates and scaler entries. Between stored values, only
the per-coordinate target mean/scale is linearly interpolated before inverse
scaling; the decoder itself is evaluated at the requested coordinate. Values
outside the stored axis range are decoder extrapolation, with endpoint-clamped
scaler values. This query path is additive: training, checkpoint serialization,
full-grid reconstruction, optimizer prediction, and audit behavior remain
unchanged.

Ensemble members may bootstrap real rows and use configured latent, embedding,
Fourier-feature, hidden-layer, batch, optimizer, and non-finite policies. Member
spread is exposed as an uncalibrated diagnostic and is not durable truth. The live
GPSAF survival path selects from mean predicted costs only; member min/max spread
does not affect selected candidates.

## Scheduling and recovery

Runtime state and training schedules are keyed by effective workspace/checkpoint
paths plus active strategy and `conditional-inr` component identities. At most one
background training task runs for the active workspace strategy. Real jobs are
submitted first, then training may use the waiting interval; maximum generation lag
bounds stale models. An asynchronous trainer receives an owned task snapshot and
training bundle rather than reopening mutable task files. Switching strategies
waits and releases memory while retaining disk state; explicit history clearing
removes all derived namespaces separately.

Checkpoints use an explicit format version, `conditional_inr` method,
`real_field_balanced` policy, semantic state signature, and run/component namespace.
The signature includes the strategy signature and parameter ranges/levels because they define normalized-input
meaning. Publication renames the complete artifact tree, writes a root convenience
pointer, then atomically writes the unique namespace manifest as the commit record.
Readers recover committed publications only from
`runs/<strategy>/components/conditional-inr/`; a
failed root/commit write cannot expose a partial model, and switching away and back
can recover the retained compatible publication. Incompatible and interrupted
artifacts remain retained but inactive. Current `submit/calc_cost.py` is reapplied to
predicted rawData after recovery, so cost policy is never frozen in a checkpoint.

## Invariants

- No direct authoritative `variables -> cost` model path.
- No checkpoint or scheduler collision across workspaces.
- Training never needs to scan history per candidate and never depends on a segment
  being published before a current accepted row becomes useful.
- Non-finite/corrupt history is diagnosed and bounded by policy.
- Prediction output passes the same rawData/cost interpretation used for real data.
- Full-grid prediction never routes through optional off-grid interpolation.
