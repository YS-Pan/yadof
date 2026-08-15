# Module blueprint: recorded_data

## Responsibility and files

`yadof.recorded_data` owns durable workspace evidence and one explicit campaign
session. Paths are derived only from the effective workspace. V2 individual
evidence is stored in immutable standard-ZIP micro-batch segments; optimization and
surrogate metadata uses unique immutable JSON event files.

## Recording contract

Owned envelopes store raw variables once per individual, job/run/generation
provenance,
workflow timing, status, and diagnostic metadata. RawData member metadata is scrubbed
of repeated variable payloads before archiving. Normalized variables, current costs,
and surrogate predictions are not persisted as source truth.

Current cost is finalized before admission. Error/timeout rows may have no rawData;
completed evidence must satisfy the current rawData schema. A non-blocking offer
reserves both a candidate credit and conservative peak-resident byte credits.

Sources may be file-backed direct `.npz` paths or named in-memory payloads. The
recording layer validates memory payloads, canonicalizes metadata, rejects any field
that would require pickle, encodes NPZ bytes, and writes the same
candidate-scoped standard-ZIP member shape. Workers never write segments.

`CampaignSession` discovers finalized segment names once, builds a private hot
catalog, validates stable parameter identity/objective width at generation
boundaries, and owns exactly one bounded daemon writer. The writer publishes up to
the configured count/byte target through a same-directory temporary ZIP and atomic
rename; it never opens an older segment. Queue refusal, oversize, write failure,
circuit-break disablement, writer death, and bounded shutdown are counters and
warnings rather than evaluation failures.

## Queries

Public queries list/filter records, recover raw variables, load segment members,
derive current normalized variables and costs through `job_template`, and assemble
training bundles. Invalid, legacy, missing, or corrupt rawData is skipped with
diagnostics rather than poisoning all history. Objective changes are reflected on
the next query because costs are recalculated. Historical-result queries accept an
optional `(completed, total, message)` callback covering reinterpretation; omitting
it preserves the normal quiet API. Temporary and legacy global-ZIP/JSONL files are
ignored. Candidate/member failure skips that candidate where siblings remain
readable; central-directory/manifest failure skips one segment.

## Invariants

- One OS lock and one writer exist per active workspace campaign; separate
  workspaces remain independent.
- Published segments are immutable, versioned, finalized only by atomic rename,
  and bounded by campaign-selected count/byte policy.
- In-flight envelopes stay within the complete unpublished count/byte budget.
- A dropped current row may remain in derived hot history only while its existing
  interpretation remains valid; a later reinterpretation removes it.
- Clearing history validates exact workspace-owned v2 targets, requires user
  confirmation, refuses an active lock, and leaves legacy data untouched.
