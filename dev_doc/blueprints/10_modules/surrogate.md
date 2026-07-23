# Module blueprint: surrogate

## Responsibility

`yadof.surrogate` models workspace rawData as a function of normalized variables and
rawData query coordinates. It trains a conditional implicit-neural-representation
ensemble, reconstructs predicted rawData, calculates current costs through
`job_template`, exposes per-objective member min/max intervals, audits historical
error, and publishes recoverable checkpoints/metadata.

## Training data and model

Training bundles come from validated recorded evidence. RawData fields are flattened
into query-aligned numeric slots with schema/axis identity; target scaling handles
constant or near-constant fields. Task-owned importance weights may emphasize
objective-relevant windows while retaining full-field coverage. Large fields may use
stochastic query minibatches for training, but public prediction reconstructs the
full compatible field.

Ensemble members may bootstrap samples and use configured latent, embedding,
Fourier-feature, hidden-layer, batch, optimizer, and non-finite policies. Member
spread becomes uncertainty input for optimizer screening; it is not durable truth.

## Scheduling and recovery

Runtime state and training schedules are keyed by effective workspace/checkpoint
paths. At most one background training task runs per workspace. Real jobs are
submitted first, then training may use the waiting interval; maximum generation lag
bounds stale models. Clearing one workspace waits/resets only that workspace.

Checkpoints contain model artifacts, auxiliary arrays, parameter/rawData signatures,
generation identity, config summary, and audit metadata. Recovery requires
compatible current parameters/rawData schema. Current `calc_cost.py` is reapplied to
predicted rawData after recovery, so cost policy is never frozen in a checkpoint.

## Invariants

- No direct authoritative `variables -> cost` model path.
- No checkpoint or scheduler collision across workspaces.
- Non-finite/corrupt history is diagnosed and bounded by policy.
- Prediction output passes the same rawData/cost interpretation used for real data.
