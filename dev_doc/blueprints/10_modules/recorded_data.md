# Module blueprint: recorded_data

## Responsibility and files

`yadof.recorded_data` owns durable workspace evidence. Compact individual rows are
appended to `indMeta.jsonl`; optimization/surrogate metadata has its own manifests;
rawData is stored in a zip-based `rawData.npz` archive under job-namespaced members.
Paths are derived only from the effective workspace.

## Recording contract

Records store raw variables once per individual, job/run/generation provenance,
workflow timing, status, and diagnostic metadata. RawData member metadata is scrubbed
of repeated variable payloads before archiving. Normalized variables, current costs,
and surrogate predictions are not persisted as source truth.

Mutable archive and JSONL publication uses process-local plus file locks and atomic
replacement. A result is validated before publication. Error/timeout records may
have no rawData; completed evidence must satisfy the current rawData schema.

Sources may be file-backed direct `.npz` paths or named in-memory payloads. The
recording layer validates memory payloads, canonicalizes metadata, rejects any field
that would require pickle, encodes NPZ bytes, and writes the same
`<logical-name>/<basename>.npz` archive shape. Workers never write the archive.

`record_job_results()` is the population fast path for file-backed batches. It validates a batch, copies the
existing archive once, appends all job members, and publishes the archive and JSONL
manifest atomically under the workspace lock. Single-job recording remains available
for direct callers and per-individual fallback.

## Queries

Public queries list/filter records, recover raw variables, load archive members,
derive current normalized variables and costs through `job_template`, and assemble
training bundles. Invalid, legacy, missing, or corrupt rawData is skipped with
diagnostics rather than poisoning all history. Objective changes are reflected on
the next query because costs are recalculated.

## Invariants

- Workspace locks and files are never shared through process-global default paths.
- Archive member names are job-scoped and flat within each job namespace.
- Partial publication does not replace the last valid archive/manifest.
- Batch failure can fall back to isolated single-result publication.
- A streamed fast result can use the single-result atomic path without retaining a
  generation of memory evidence.
- Clearing history validates the exact workspace-owned targets and is user-confirmed
  through tools/CLI rather than implicit runtime cleanup.
