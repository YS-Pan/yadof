# Module blueprint: surrogate

## Responsibility

`yadof.surrogate` exposes rawData-first surrogate components plus a lightweight,
backend-neutral joint rawData posterior protocol. The production component remains
the conditional implicit-neural-representation ensemble used by workspace-owned
GPSAF. A separate opt-in `hierarchical_cae()` development component reconstructs
complete fixed-grid rawData with field-specific convolutional codecs and a joint
parameter-latent predictor. It is installable and recoverable. Its first Gate 0 v5
candidate failed the then-sealed representation and anti-noise requirements; v6/v7
later completed all-axis coordinate readout, the viewer adapter, and a fixed offline
mechanism path. Exact-signature v8 calibration failed closed and produced no usable
posterior artifact.

A fresh 24-cell base-component benchmark later found domain-dependent end-to-end
evidence: strong aggregate cost/ranking benefit on synthetic antenna, mixed SAW
results, and severe Chrono rawData/worst-field weakness. The sealed all-cell gate
remains historically false, but current planning no longer treats it as a global
performance verdict. CAE evidence is reported by case, metric, capability, and
resource tradeoff; the component remains opt-in and no result changes the production
default automatically.

The independent opt-in `pca_svd()` component is a deterministic baseline rather
than a posterior model. It fits centered PCA or uncentered truncated SVD per exact
named field, then fits one multi-output ridge map from normalized parameters to
the concatenated coefficients. A separate codec/oracle API may encode known
validation rawData and always labels that output diagnostic-only. GPSAF receives
only deployable parameter predictions and zero-width cost intervals.

PCA/SVD is also the first explicit fit/state/predict implementation. Callers
materialize an immutable `SurrogateTrainingData` from Stage 2 evidence and cost
views, or construct the same owned value directly from materialized arrays and
structured samples. Exact content and provenance have separate digests. A public
`TrainingHandle` owns asynchronous fit/cancel/wait/close behavior, and the typed
`SurrogatePrediction` owns transient complete rawData plus current-snapshot cost.
Neither the PCA/SVD component nor its recovery path scans a session implicitly.

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
- `linear_subspace/` owns validated immutable settings, per-field PCA/SVD codecs,
  diagnostic-only oracle reconstruction, deployable ridge prediction, named-schema
  adaptation, atomic no-pickle checkpoint recovery, and a generation-scoped
  explicit-handle scheduler. Its namespace is `pca-svd`; it exposes no
  posterior/readiness method.
- `training.py` owns the backend-neutral materialized input, semantic/provenance
  digests, explicit fit-handle state machine, and deterministic prediction DTO. It
  imports NumPy but not Torch and is exported by the lightweight parent package.
- `hierarchical_cae/data_filtering/` owns the component-local mode selector and
  implementations; common assessment/applicability types do not depend on a
  concrete implementation. Mode `none` is the default and returns the ordinary uniform
  training view. Mode `frequency` accepts explicit task assessments,
  declarative diagnostic rules, or task-declared shape fallback thresholds,
  including spectral high-frequency energy; it contains no task field names,
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

The factory's one authoritative `data_filter_mode` defaults to `none`. The existing
frequency-based anti-noise path is selected explicitly as `frequency` and requires
its versioned `FrequencyFilter`; a frequency filter without that mode is rejected. This local dispatch is
the extension point for future filtering methods and does not create a package-wide
registry.

Every design first produces one loss per field, independent of field point count.
Optional caps and filter weights are applied only after this matrix exists, so a
noisy curve does not discard valid scalar fields from the same design. Without a
selected filter, weights are one, shared masks are one, residual targets are zero,
and the behavior is an ordinary equal field macro loss.

With a frequency filter, explicit version/filter-matched assessment has priority over task
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
complete data-filter mode and frequency-filter declaration. Checkpoint publication is atomic and separate from
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

## Explicit PCA/SVD data and lifecycle

`materialize_training_data()` joins `EvidenceDataset` and `CostTable` only by row
identity. Default selection accepts committed original or explicit derived rows
with readable rawData and successful finite interpretation; explicit row IDs are
strict. Direct values reject lazy loaders plus object, structured, complex,
masked, or non-finite main targets. C/F source layout canonicalizes to the same
digest, while dtype, shape, row order, duplicates, status, mask, or numeric content
changes it. Source identity, lineage, and optional transform ID change only the
provenance digest.

`start_fit()` creates one non-daemon owner-thread handle. Cooperative cancellation
checks bracket model fitting and checkpoint publication; atomic commit is the
terminal race boundary. Session-backed training leases the exact current snapshot,
normal generation completion waits/closes it, and abnormal session shutdown
cancels/waits before recorder cleanup. Sync `fit()` composes this same handle path.
Recovery requires the same exact materialized data. Checkpoints store semantic
training content separately from bounded provenance and cold-fit old manifests
that lack this contract.

`predict()` consumes only an explicit `LinearSubspaceState`, normalized candidates,
and exact task snapshot. It reconstructs full rawData and reapplies that snapshot's
cost policy, yielding a frozen deterministic DTO with zero-width intervals. GPSAF
alone derives its legacy `(costs, intervals)` rows; predictions never enter the
recorder or evidence/history views. The generic viewer uses a read-only one-member
adapter over the same manifest/artifact model.

## Conditional-INR training data and model

Until the retained-capability migration stage, conditional-INR training bundles
come from the active campaign session when one exists, so finalized
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

Conditional-INR runtime state and training schedules are keyed by effective workspace/checkpoint
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
- PCA/SVD state reuse is keyed by exact materialized content; source identity and
  transform labels cannot substitute for that digest or unnecessarily invalidate
  identical mathematics.
- Explicit PCA/SVD fit/predict never scans session/history internally and never
  publishes predicted rawData.
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
- Hierarchical data-filter mode and frequency-filter changes activate the appropriate
  semantic identity; executable task callbacks cannot bypass that identity.
- A low-trust field cannot contribute unweighted tokens to shared teacher state,
  and its gated residual never becomes independent Gaussian observation noise.
- Gate 0 v5/v8 and the later 24-cell all-cell result remain immutable historical
  evidence. Current CAE research does not collapse their mixed case/metric outcomes
  into a global `performance_accepted` truth. The exact calibrated states exercised
  so far still expose no usable posterior artifact, so their production qNEHVI
  exploitation remains blocked on capability-specific readiness rather than on a
  universal CAE performance gate.
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
