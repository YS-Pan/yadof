# Module blueprint: recorded_data

## Responsibility and files

`yadof.recorded_data` owns durable workspace evidence, one explicit campaign
session, identity-preserving evidence views, and task-bound cost views. Paths are
derived only from the effective workspace. Individual evidence is stored in
immutable standard-ZIP micro-batch segments; optimization and surrogate metadata
uses unique immutable JSON event files.
The native layout is directly `recorded_data/segments/` and
`recorded_data/metadata/`; neither paths nor record JSON add a recorded-data version
layer. Segment format identity and structural/member validation remain explicit,
while each embedded rawData NPZ keeps its independent schema contract.

## Recording contract

Owned envelopes store raw variables once per individual, job/run/generation
provenance,
workflow timing, status, and diagnostic metadata. RawData member metadata is scrubbed
of repeated variable payloads before archiving. Normalized variables, current costs,
and surrogate predictions are not persisted as source truth.

Current cost is never source truth and is not required for admission.
Error/timeout/cancelled rows may have no rawData; completed evidence must satisfy
the current rawData schema.
Admission returns a candidate/group receipt and reserves both a candidate credit and
conservative peak-resident byte credits. A full budget blocks the producer until
publication releases capacity; it never drops a row. The receipt remains pending
through queue admission and resolves committed only after atomic segment
publication. Failed publication resolves every affected receipt failed.

Sources may be file-backed direct `.npz` paths or named in-memory payloads. The
recording layer validates memory payloads, canonicalizes metadata, rejects any field
that would require pickle, encodes NPZ bytes, and writes the same
candidate-scoped standard-ZIP member shape. Workers never write segments.

`CampaignSession` discovers finalized segment names once, builds a private hot
catalog, validates stable parameter identity/objective width at generation
boundaries, and owns exactly one bounded writer. Committed-but-uninterpreted payload
ownership reuses the configured unpublished count/byte limits; payloads beyond that
resident budget are recovered from their new immutable segment rather than retained
in another unbounded memory queue. The writer publishes up to the
configured count/byte target through a same-directory temporary ZIP and atomic
rename; it never opens an older segment. Evaluation/population boundaries wait for
all pending segments. The writer retries the same retained batch after a transient
write failure; an oversized envelope, exhausted retry count, or unexpected writer
death raises `RecordingError` and prevents later evaluation.

The session also retains open generation-handle leases for its exact current task
snapshot. Each registration declares a normal-boundary policy: explicit surrogate
training waits/closes, while evaluation uses cancellation-close after its owning
composition has already waited. A new generation is rejected until the registry is
empty. `finish_generation()` resolves those policies without holding the state
lock. Shutdown first cancels/closes a copied handle set, then shuts down
the writer, releases the workspace lock, and removes snapshots; standalone handles
own and close their private session instead of self-registering recursively.

## Evidence and cost views

`EvidenceDataset` is an immutable ordered metadata/provenance view. Original rows
reuse the durable candidate identity for `candidate_id`, `evidence_id`, and
`row_id`; a separate canonical design key may match duplicate physical designs but
never merges them. Selection, filtering, copying, and cost joins preserve row
identity. Durable and committed-live rows hold only lazy `SegmentReference`-backed
rawData handles; pending rows have no readable handle.

`CostTable` binds ordered interpretation rows to the task interpretation
fingerprint and objective schema. Successful rows contain finite costs of the
declared width. Failed, not-applicable, and missing rows keep `None` costs plus
bounded diagnostics; only `to_optimizer_costs()` maps them to correct-width `inf`.
Interpretation loads and releases at most one candidate payload at a time and never
updates a segment.

`derive_evidence_row()` owns one explicit transformed rawData copy and gives it a
deterministic row identity from parent ID, operation, JSON-safe parameters,
ordinal, and semantic content digest. Derived rows retain lineage and root evidence
identity but remain transient and cannot enter recorder or committed history.

## Queries

Public queries list/filter records, recover raw variables, load segment members,
produce evidence/cost views, and assemble compatibility training bundles.
Historical result, cost, and surrogate-training adapters use identity joins
internally while retaining their existing tuple/dict shapes. Named training reads
preserve every direct NPZ basename and expose copied JSON-safe `job_metadata`
aligned to the same accepted evidence rows, allowing task-owned hierarchical-CAE
filters to consume diagnostics without altering rawData. The live campaign exposes
the same schema over durable plus accepted current rows; pending evidence is
visible in its dataset but is not a readable sample or optimizer-history row.

The public surrogate materializer consumes these same dataset/table values and
strictly joins by row ID. It owns copied structured rawData and bounded provenance;
it does not add a persistence format, rewrite a segment, or record a derived row.

The cost-view reader freezes one finalized segment-name snapshot, then opens each
selected ZIP once to combine manifest checks, NPZ decode/schema validation, and
current-cost input delivery. Invalid, missing, or corrupt rawData is isolated with
diagnostics rather than poisoning all history. Objective changes are reflected on
the next table because costs are recalculated. Historical-result queries accept an
optional `(completed, total, message)` callback covering reinterpretation; omitting
it preserves the normal quiet API. Temporary and unrelated files are ignored.
Candidate/member failure skips that candidate where siblings remain
readable; central-directory/manifest failure skips one segment.

## Invariants

- One OS lock and one writer exist per active workspace campaign; separate
  workspaces remain independent.
- Published segments are immutable, finalized only by atomic rename,
  and bounded by campaign-selected count/byte policy.
- In-flight envelopes stay within the complete unpublished count/byte budget.
- Committed owned payloads stay within an explicit count/byte budget; logical
  population ordering may retain only payload-free result metadata and durable
  references beyond it.
- Every prepared current row is either durably published before the next
  population boundary or the campaign stops with a recording error.
- Immutable completed evidence is independent from transient normalization, cost,
  and interpretation diagnostics; a failed cost can be replayed under a later
  generation snapshot.
- Original evidence identity is never inferred from job name, design key, view
  position, or normalized variables; cost/history consumers join by row ID.
- Dataset view operations do not decode rawData, and derived/transformed rows never
  publish themselves or become committed optimizer history.
- A live campaign rejects a duplicate candidate identity before recorder admission;
  it never publishes a duplicate that a later first-wins query would ignore.
- Clearing history validates the exact workspace-owned segment and event targets,
  requires user confirmation, refuses an active lock, and leaves unrelated entries
  untouched.
- Named rawData and record metadata queries are read-only derived views. Metadata
  never replaces rawData, changes current cost, or creates a second evidence store.
- Generation-handle waits/cancellation happen outside the session state lock and
  all handles close before writer/snapshot teardown.
