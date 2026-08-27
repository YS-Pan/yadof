# Module blueprint: surrogate

## Responsibility

`yadof.surrogate` exposes rawData-first surrogate components plus a lightweight,
backend-neutral joint rawData posterior protocol. The existing concrete component
trains a conditional implicit-neural-representation ensemble, reconstructs predicted
rawData, calculates current costs through `job_template`, exposes per-objective
member min/max spread diagnostics, and publishes recoverable checkpoints/metadata.
Its public factory remains the narrow component injected by workspace-owned GPSAF
composition; the new posterior protocol does not change that component or make a
posterior-assisted strategy available by itself.

## Source structure

- Parent `__init__.py` and `api.py` own only the lightweight public component,
  posterior protocol exports, and lazy forwarding surface.
- `posterior.py` owns runtime-checkable surrogate/sampler/posterior protocols,
  persistent draw containers, JSON-safe support diagnostics, semantic capability
  identity, and the draw/candidate-chunk streaming projection helper. It imports no
  Torch, BoTorch, pymoo algorithm, or concrete surrogate runtime.
- `conditional_inr/` owns model construction/training, rawData adaptation,
  runtime state, staggered scheduling, checkpoint publication, metadata, the
  private finite-member posterior adapter, and private in-memory types.
- Importing the parent package must not load Torch. The public
  `conditional_inr()` factory remains callable even after private
  `surrogate.conditional_inr.*` modules are loaded.

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
