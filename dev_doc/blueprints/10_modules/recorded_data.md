# Module blueprint: recorded_data

## Responsibility and files

`yadof.recorded_data` owns durable workspace evidence and one explicit campaign
session. Paths are derived only from the effective workspace. Individual evidence
is stored in immutable standard-ZIP micro-batch segments; optimization and surrogate
metadata uses unique immutable JSON event files.
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

Current cost is finalized before admission. Error/timeout rows may have no rawData;
completed evidence must satisfy the current rawData schema. Admission reserves both
a candidate credit and conservative peak-resident byte credits. A full budget
blocks the producer until publication releases capacity; it never drops a row.

Sources may be file-backed direct `.npz` paths or named in-memory payloads. The
recording layer validates memory payloads, canonicalizes metadata, rejects any field
that would require pickle, encodes NPZ bytes, and writes the same
candidate-scoped standard-ZIP member shape. Workers never write segments.

`CampaignSession` discovers finalized segment names once, builds a private hot
catalog, validates stable parameter identity/objective width at generation
boundaries, and owns exactly one bounded writer. The writer publishes up to the
configured count/byte target through a same-directory temporary ZIP and atomic
rename; it never opens an older segment. Evaluation/population boundaries wait for
all pending segments. The writer retries the same retained batch after a transient
write failure; an oversized envelope, exhausted retry count, or unexpected writer
death raises `RecordingError` and prevents later evaluation.

## Queries

Public queries list/filter records, recover raw variables, load segment members,
derive current normalized variables and costs through `job_template`, and assemble
training bundles. The cost-view reader freezes one finalized segment-name snapshot,
then opens each selected ZIP once to combine manifest checks, NPZ decode/schema
validation, and current-cost input delivery. Invalid, missing, or corrupt rawData is skipped with
diagnostics rather than poisoning all history. Objective changes are reflected on
the next query because costs are recalculated. Historical-result queries accept an
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
- Every finalized current row is either durably published before the next
  population boundary or the campaign stops with a recording error.
- A live campaign rejects a duplicate candidate identity before recorder admission;
  it never publishes a duplicate that a later first-wins query would ignore.
- Clearing history validates the exact workspace-owned segment and event targets,
  requires user confirmation, refuses an active lock, and leaves unrelated entries
  untouched.
