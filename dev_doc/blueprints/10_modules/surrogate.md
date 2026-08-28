# Module blueprint: surrogate

## Responsibility

`yadof.surrogate` exposes rawData-first surrogate components plus a lightweight,
backend-neutral joint rawData posterior protocol. The production component remains
the conditional implicit-neural-representation ensemble used by workspace-owned
GPSAF. A separate opt-in `hierarchical_cae()` development component reconstructs
complete fixed-grid rawData with field-specific convolutional codecs and a joint
parameter-latent predictor. It is installable and recoverable, but its first
1000/2000-design Gate 0 v5 candidate failed representation and clean-target leakage
requirements. Gate 0 v6/v7 subsequently completed its all-axis coordinate readout,
viewer adapter, and fixed offline mechanism path under the explicit status
`experimental / performance-not-accepted`; none is a production default.
Gate 0 v8 subsequently exercised exact-signature held-out calibration, but every
rawData/applicability capability failed closed; this did not change v5 or create a
production artifact.

## Source structure

- Parent `__init__.py` and `api.py` own only the lightweight public component,
  posterior protocol exports, and lazy forwarding surface.
- `posterior.py` owns runtime-checkable surrogate/sampler/posterior protocols,
  persistent draw containers, JSON-safe support diagnostics, semantic capability
  identity, and the draw/candidate-chunk streaming projection helper. It imports no
  Torch, BoTorch, pymoo algorithm, or concrete surrogate runtime.
- `calibration.py` owns immutable exact-signature calibration adjuncts,
  conservative field-spread fitting, monotone member-level applicability fitting,
  and coherent calibrated sampler wrapping. It is backend-neutral and cannot
  promote, mutate, or transfer a concrete surrogate checkpoint.
- `conditional_inr/` owns model construction/training, rawData adaptation,
  runtime state, staggered scheduling, checkpoint publication, metadata, the
  private finite-member posterior adapter, and private in-memory types.
- `quality.py` owns the generic, versioned, JSON-safe quality/regime assessment
  protocol. It accepts explicit task assessments, declarative diagnostic rules, or
  task-declared shape fallback thresholds; it contains no task field names,
  simulator thresholds, cost filter, or arbitrary callback.
- `_shared/` owns only behavior-equivalent atomic artifact publication, bounded
  training-event recording, and deterministic finite-member selection. It owns no
  model/schema/namespace/quality/scheduler/selector policy.
- `hierarchical_cae/` separates schema/types, networks, pure objectives, staged
  training, bundle inference, data adaptation, state repository, projection,
  checkpoint policy, scheduler, and persistent posterior adapter behind a narrow
  lifecycle facade.
- Importing the parent package must not load Torch. The public
  `conditional_inr()` factory remains callable even after private
  concrete packages are loaded.

## Hierarchical CAE development component

Every design first produces one loss per field, independent of field point count.
Optional caps and policy weights are applied only after this matrix exists, so a
noisy curve does not discard valid scalar fields from the same design. Without a
quality policy, weights are one, shared masks are one, residual targets are zero,
and the behavior is an ordinary equal field macro loss.

With a policy, explicit version/policy-matched assessment has priority over task
diagnostics; declarative morphology rules run only when the selected missing-data
policy allows them. Low-trust tokens are masked before shared teacher fusion. Base
decoder gradients are similarly masked for those fields, while chatter/failure
targets can train a field-private residual decoder. Predictor members emit one
joint latent, an uncalibrated `P(smooth)`, and field residual logits. A smooth gate
is structurally zero in teacher training, and inference gates only the private
residual. Raw evidence is never smoothed or rewritten and current `calc_cost.py`
always receives reconstructed full-grid rawData.

Schema identity includes exact selectors, shapes, dtypes, axes, axis encodings,
rank-3 channel/spatial roles, groups, scalers, training/head/loss switches, and the
complete quality policy. Checkpoint publication is atomic and separate from
conditional-INR namespaces. Predictor members share codecs; each persistent draw
fixes one member across candidates and fields and reports finite support with zero
observation noise. Applicability is not calibrated in this module.

## Joint posterior contract

A posterior-capable component implements an explicit
`RawDataPosteriorSurrogate`, including its normal component semantic identity, a
posterior-capability semantic identity block, and `make_rawdata_sampler()`. The
sampler fixes requested draw IDs and underlying support sources at creation. Every
later `predict(candidate_chunk)` returns the same ordered draws, so repeated
candidates, candidate permutations, chunk sizes, and chunk call order cannot
resample a function.

One `RawDataFunctionDraw` carries one complete structured sample per candidate.
Fields are identified only by `(direct .npz basename including .npz, resolved
values/data main key)`. `RawDataPosteriorDiagnostics` records posterior kind,
requested/actual draw counts, seed, draw/source IDs, honest `finite` versus
`continuous_or_unknown` support, schema/state/strategy signatures, approximation
limits, observation-noise status, supported selectors, candidate count, bounded
failures, and per-evaluation effective support. Continuous/unknown support uses
`unique_support=None`; repeated draws from a finite ensemble do not increase its
integer support. Effective finite support counts distinct drawn sources that remain
complete for the requested candidates and, after projection, current cost.

A calibrated finite sampler additionally enumerates every unique member exactly
once and carries a self-verifying calibration-artifact hash and method version in
diagnostics. The adjunct scales each complete field around the unchanged empirical
mean without changing the shared draw axis. Artifact state/strategy/schema/support,
checkpoint hashes, training provenance, calibration partition, policy, and
label/head/loss identity must all match; otherwise calibration is unavailable.

`project_rawdata_sampler()` streams candidate chunks and then individual draws
through an injected `RawDataCostProjector`. It retains only
`[draw,candidate,objective]`, valid masks, and bounded diagnostics. Posterior rawData
never enters finalization or recording. A component/backend version or controlled
posterior parameter belongs in the component/strategy semantic identity. The
explicit `conditional_inr_posterior()` wrapper has its own component/capability
identity and cannot alter the existing conditional-INR GPSAF identity unless that
wrapper is explicitly selected by another strategy.

## Conditional-INR posterior adapter

The adapter obtains exact direct `.npz` basenames from transient named campaign
evidence and combines them with the trained state's frozen templates. It rejects a
state whose modeled slot is not the resolved main array because posterior axes,
units, and metadata must remain frozen. A seeded permutation-cycle policy fixes one
loaded ensemble member for every requested draw. Repeated cycles preserve their
member source IDs and never inflate nominal support.

Each distinct `(member, normalized candidate)` is inferred once per `predict()`
call using the existing selected-member forward/scaler path, then reconstructed on
the full stored grid. One-row inference makes the result independent of candidate
batch composition as well as chunk order/size. A member/candidate failure yields an
invalid complete sample for every draw using that member; no other member can fill
one of its fields. The adapter remains uncalibrated, includes no observation noise,
and does not change mean rawData, mean costs, min/max intervals, viewer behavior,
model architecture, or checkpoint mathematics.

## Training data and model

Training bundles come from the active campaign session when one exists, so finalized
segments and accepted unpublished current rows share one validated view. Outside a
campaign they come from tolerant public recorded-data queries. RawData fields are flattened
into query-aligned numeric slots with schema/axis identity; target scaling handles
constant or near-constant fields. Each query position is centered by its recorded
mean and divided by its recorded standard deviation with a configured floor.
Normalized design inputs are centered to `[-1, 1]`, and the conditional decoder has
an unbounded linear output in standard-score space so useful rawData extrapolation
is not clipped to observed extrema. Training targets are only recorded real rows or
seeded bootstrap draws from them. Query minibatches are seeded, balanced across
active fields, and sampled without replacement inside each field. Each field owns
one seeded coordinate ordering; successive steps continue from the previous cursor
so all available coordinates are covered before that ordering repeats. Pointwise
Smooth L1 is averaged within each field and then macro-averaged equally across fields.
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
Fourier-feature, hidden-layer, batch, optimizer, and non-finite policies. A sparse
history with fewer than two real rows per normalized input dimension keeps every
row visible to every member even when bootstrap is requested; independent
initialization retains ensemble diversity until ordinary resampling no longer
throws away scarce design support. Member spread is exposed as an uncalibrated
diagnostic and is not durable truth. The live
GPSAF survival path selects from mean predicted costs only; member min/max spread
does not affect selected candidates.

## Scheduling and recovery

Runtime state and training schedules are keyed by effective workspace/checkpoint
paths plus active strategy and `conditional-inr` component identities. At most one
background training task runs for the active workspace strategy. Real jobs are
submitted first, then training may use the waiting interval; maximum generation lag
bounds stale models, with a package default of one generation. An asynchronous
trainer receives an owned task snapshot and
training bundle rather than reopening mutable task files. Switching strategies
waits and releases memory while retaining disk state; explicit history clearing
removes all derived namespaces separately.

Checkpoints use the `conditional_inr` method, `real_field_balanced` policy,
semantic state signature, and run/component namespace.
The signature includes the strategy signature and parameter ranges/levels because they define normalized-input
meaning. Publication renames the complete artifact tree, writes a root convenience
pointer, then atomically writes the unique namespace manifest as the commit record.
Readers recover committed publications only from
`runs/<strategy>/components/conditional-inr/`; a
failed root/commit write cannot expose a partial model, and switching away and back
can recover the retained compatible publication. Incompatible and interrupted
artifacts remain retained but inactive. Current `submit/calc_cost.py` is reapplied to
predicted rawData after recovery, so cost policy is never frozen in a checkpoint.
The model artifact records an explicit architecture version; incompatible bounded-
output artifacts cold-train instead of being interpreted with the linear decoder.

## Invariants

- No direct authoritative `variables -> cost` model path.
- No checkpoint or scheduler collision across workspaces.
- Training never needs to scan history per candidate and never depends on a segment
  being published before a current accepted row becomes useful.
- Non-finite/corrupt history is diagnosed and bounded by policy.
- Prediction output passes the same rawData/cost interpretation used for real data.
- Full-grid prediction never routes through optional off-grid interpolation.
- Function draw identity is stable across every candidate and field in one sampler;
  independent row/field/objective resampling violates the protocol.
- Parent imports expose the protocol without loading any optional numerical backend.
- Conditional-INR's old mean-cost/min-max tuple, GPSAF behavior, model architecture
  version, and checkpoint signature remain unchanged by the separately identified
  posterior adapter.
- Hierarchical quality policy changes activate a different semantic namespace;
  executable task callbacks cannot bypass that identity.
- A low-trust field cannot contribute unweighted tokens to shared teacher state,
  and its gated residual never becomes independent Gaussian observation noise.
- Gate 0 v5's performance failure remains immutable. Gate 0 v6/v7 separately permits
  the coordinate readout, viewer integration, and one fixed offline-test path only as
  experimental mechanism evidence. Gate 0 v8 used a new pre-access registration
  bound to durable exact states, but all calibration artifacts failed closed;
  production qNEHVI exploitation remains blocked until a performance-accepted
  architecture and usable independent calibration exist.
- `PosteriorExploitationReadiness` is the only optimizer-facing typed authorization:
  it aligns one normalized pool with performance/posterior/applicability status,
  transferability, zero-noise state/artifact signatures, calibrated probabilities,
  and explicit failure reasons. It contains no member variance or loss field.
  Current conditional-INR and hierarchical components expose static/runtime blocked
  readiness without invoking their uncalibrated applicability heads.
- A successful 082609 calibration artifact remains
  `experimental-performance-not-accepted` and non-transferable; it is probability
  capability evidence for one exact state, not architecture acceptance or full
  qNEHVI strategy authorization.

Hierarchical and conditional checkpoints call the same atomic write/publication
primitive but keep distinct component namespaces and semantic payloads. Their
training success/failure events share a bounded writer, and their posterior
adapters share seeded permutation-cycle member selection. Scheduler extraction was
deliberately rejected because workspace freshness/deactivation/callback policy is
not behavior-equivalent without a callback-heavy abstraction.
