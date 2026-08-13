# Unify Loss-Tolerant Evaluation Recording

## Context

### Why this work is needed

Yadof intends fast, local, and distributed evaluation to differ only in execution
transport. Once a backend has produced a backend-neutral result, validation, cost
calculation, recording, population ordering, and failure isolation should have one
meaning. The current implementation does not fully satisfy that intent:

- local and distributed evaluation collect a population and normally call the
  batch `record_results()` path;
- fast evaluation calls the single-result `record_result()` path synchronously from
  each worker-completion callback;
- both paths ultimately mutate the same campaign-wide `recorded_data/rawData.npz`
  archive and rewrite campaign-wide JSONL metadata.

The current single-result publication algorithm reads the existing individual
manifest, copies the complete existing rawData archive to a temporary file, appends
one candidate, rewrites the complete manifest, and atomically replaces both files.
Batch publication reduces that cost to once per population, but it still copies an
archive whose size grows with the complete campaign. The resulting write cost is
therefore coupled to historical campaign size rather than to the size of the new
candidate evidence.

Fast mode exposes the problem most strongly. `fast_runner.py` invokes the result
consumer before it releases the worker slot or resumes draining other worker pipes.
The consumer records the candidate and recalculates cost through recorded history.
When recording grows slower, already-completed workers wait behind parent-side I/O,
and their scheduler-observed elapsed time includes that wait. This makes a constant-
time simulator look progressively slower and prevents reusable workers from being
kept busy.

### Reproduction evidence

The `20260807 saw` workspace produced 5,000 records over 50 generations. Its
existing history showed:

| Measurement | Generation 0 | Generation 49 |
|---|---:|---:|
| Mean ngspice simulation time | 0.091 s | 0.080 s |
| Mean fast worker time | 0.106 s | 0.094 s |
| Mean recorded individual `elapsed_time` | 0.505 s | 5.755 s |
| Whole-generation wall time | 13.728 s | 166.624 s |

Generation wall time fit approximately
`15.437 + 3.062 * generation_index` seconds with `R^2 = 0.9973`, while the actual
simulation time stayed flat or improved. At the end of the run,
`recorded_data/rawData.npz` was about 147.9 MB and `indMeta.jsonl` was about
22.1 MB. Repeated atomic replacement implied roughly 369.6 GB of cumulative
rawData archive copying and 55.2 GB of cumulative metadata rewriting. The same run
contained no scratch-cleanup errors, left no fast scratch directory, and never
observed more than the expected worker-plus-simulator process tree, excluding
simulator, descendant-process, and scratch accumulation as the cause.

The run also contained three successful evaluations that became recorded-data
errors after Windows denied an `indMeta.jsonl` temporary-file replacement. This is
a second symptom of the same design: a central mutable publication failure can
change an otherwise usable evaluation into an optimization failure.

### Product decisions governing the redesign

This future work is intentionally allowed to make a large change and to replace the
current history format without a compatibility reader or migration path. It must
follow these decisions:

1. Fast, local, and distributed evaluation use one post-execution finalization and
   one recording implementation. Backend-specific orchestration must stop at a
   backend-neutral result boundary.
2. Losing a small number of candidate records is acceptable. The evolutionary,
   generation-based optimizer is expected to tolerate missing samples.
3. A recording failure, full recording queue, corrupt record, unavailable history,
   broken index, permission error, or exhausted history volume must not crash or
   stop optimization. Evaluation and subsequent generations must continue.
4. The main evaluation path must not wait indefinitely for durability. Bounded loss
   is preferable to allowing storage latency or failure to control simulator
   throughput.

These decisions deliberately replace the existing evidence-first rule that a
completed result must be published before its cost can be returned. RawData remains
the scientific input to cost calculation and, when successfully persisted, remains
available for later reinterpretation. Durability itself is no longer a prerequisite
for using the current evaluation in the running optimizer.

## Goal

Implement one backend-neutral, loss-tolerant result pipeline with these properties:

```text
fast/local/distributed backend
  -> backend-neutral JobResult
  -> common rawData validation and current cost calculation
  -> ordered EvaluationOutcome returned to optimizer
  -> best-effort bounded recording enqueue
  -> asynchronous immutable micro-batch segment publication
  -> optional rebuildable query index
```

When the work is complete:

- amortized publication work is proportional to newly recorded candidate bytes,
  not to the number or total size of earlier candidates;
- no backend contains its own persistence policy or directly calls a single/batch
  history writer;
- a valid evaluation can contribute its current cost to the optimizer even if its
  durable record is dropped or cannot be written;
- corrupt or missing stored candidates are isolated and skipped, leaving every
  other valid candidate usable;
- recording work has bounded memory, bounded shutdown delay, bounded retries, and
  no path by which its failure can terminate an optimization campaign;
- history and surrogate consumers accept partial or empty history and degrade to a
  safe cold-start or real-evaluation path.

The performance intent is to remove algorithmic history-size growth from the write
path. It does not promise that simulation and recording can never contend for the
same physical CPU, memory, or disk bandwidth. The queue and writer must prevent
that contention from becoming unbounded backpressure or a synchronous dependency
on the total campaign history.

## Guidance

### 1. Establish one common outcome finalizer

Move all post-execution behavior behind one component called by fast, local, and
distributed orchestration. A backend may prepare, execute, time out, retry, or
collect differently, but it should only return a `JobResult` containing identity,
status, raw variables, diagnostics, and either file-backed or memory-backed
rawData.

The common finalizer should:

1. validate the backend-neutral rawData source;
2. calculate the current objective tuple directly from that source and the current
   workspace task definition, without first reopening durable history;
3. construct an ordered `EvaluationOutcome` containing the current costs and the
   diagnostic result;
4. hand the outcome to the optimizer/progress path immediately;
5. offer an owned record envelope to the best-effort recorder without blocking on
   campaign history publication.

The finalizer must define source lifetime explicitly. Memory-backed fast payloads
must remain owned until the recorder either publishes or drops them. File-backed
local/distributed sources must remain readable for the same interval; a later job-
cleanup feature must not delete those files while a queued envelope still refers to
them. Envelopes should carry a measured or conservatively estimated byte size so
the queue can bound total memory rather than only item count.

Cost-calculation failure remains an evaluation failure and returns the current
objective-width `inf` sentinel. Recording failure does not alter a successfully
calculated finite cost. Strict all-infinite behavior must be based on execution,
rawData, and cost failures, never on persistence loss.

### 2. Replace global mutable history with immutable candidate frames and segments

Do not retain a campaign-wide rawData ZIP or a campaign-wide individual JSONL as
the authoritative store. Keep one self-contained logical record per candidate, but
do not require one filesystem file or one durability transaction per candidate.
The recorder should pack a bounded micro-batch of independently framed candidate
records into one immutable segment. A suggested physical organization is:

```text
recorded_data/
  segments/
    <run-id>/
      generation_000000/
        segment_000000.yadseg
        segment_000001.yadseg
      generation_000001/
        segment_000000.yadseg
  cache/
    history_index.sqlite
```

The exact extension and container encoding may change during implementation. A
segment should be a sequential container whose candidate frames are independently
length-delimited and checksummed. Compression should be per candidate frame or per
rawData payload rather than one indivisible whole-segment compression stream, so a
bad candidate can be skipped without making valid siblings undecodable. A compact
footer/index may contain candidate identities, offsets, sizes, and checksums; its
absence or corruption must make the reader skip or boundedly salvage the segment,
never crash. A candidate frame should contain, as applicable:

- format/schema version and a collision-resistant candidate identity;
- run, optimization, generation, and population identities;
- raw variables and task/static signatures required to interpret compatibility;
- status, timestamps, execution provenance, bounded diagnostics, and failure data;
- every schema-valid rawData item needed for later current-cost reinterpretation;
- optionally, the cost and objective/task signature observed at evaluation time as
  a diagnostic cache. A stored cost must never become scientific source truth or
  silently override recalculation through the current compatible `calc_cost.py`.

Use same-directory temporary creation followed by atomic replacement of one whole
segment. A finalized segment is never reopened for mutation. Readers ignore
temporary files. Failure before replacement loses at most that bounded micro-batch;
it cannot make an earlier segment unreadable. Segment and candidate identities must
not rely solely on a user/job name that can collide across resumes or concurrent
calls. The selected item/byte/time flush limits therefore also define the maximum
normal-process loss domain and must be visible in configuration or diagnostics.

Do not use an append-open campaign ZIP, one compression stream spanning the whole
campaign, or one file per candidate as the default physical layout. The first two
recreate a central mutable failure domain; the last avoids campaign-size copying
but performs poorly on rotational media because every small record causes file and
directory metadata work plus additional seeks. Per-candidate files may remain only
as a focused test codec or deliberately selected debugging mode, not as the normal
writer.

Apply the same immutable-event principle to run/generation/surrogate metadata that
would otherwise recreate a growing central rewrite. It is acceptable to maintain
derived summaries, but they cannot be required to recover authoritative candidate
records.

### 3. Make asynchronous recording bounded and explicitly lossy

Use one workspace-scoped recorder service for every evaluation backend. A dedicated
thread or process is an implementation choice, but exceptions must be contained
inside a supervised boundary and must never escape into evaluation or optimization
control flow.

The recorder must have both an item-count limit and a byte limit. Enqueue is
non-blocking or has only a small fixed upper bound. Required behavior is:

- when capacity is available, transfer the envelope to the recorder;
- when the queue is full, drop the new envelope (or apply one documented stable
  drop policy), increment in-memory loss counters, issue a rate-limited warning,
  and continue evaluation;
- on a write, permission, encoding, checksum, or atomic-replace failure, isolate
  that envelope, increment failure counters, and continue consuming later items;
- after repeated systemic failures, use a circuit breaker to disable or cool down
  recording for the workspace rather than retrying without bound;
- at normal process shutdown, attempt a bounded drain; once the deadline expires,
  discard the remainder and let the program exit;
- if the recorder itself exits unexpectedly, detect it, disable or perform a
  bounded restart according to a documented policy, and keep optimization alive.

Warnings and summaries are observability, not another durability dependency. If
stderr/log reporting fails, the campaign still continues. Expose concise counters
such as enqueued, published, queue-dropped, write-failed, and shutdown-dropped in
progress/final diagnostics when available. Do not print one unbounded traceback per
lost candidate.

Default queue limits should permit normal simulator throughput without allowing
large rawData to exhaust host memory. If they are configurable, validation must
reject unbounded values and configuration must remain common to all three backends.

Queue ownership should reuse the validation/cost read whenever practical. The
common finalizer should produce one canonical owned envelope instead of forcing the
writer to reopen scattered local/distributed job files after cost calculation.
Fast memory payloads and local/distributed file payloads must converge to the same
owned envelope representation before queue admission. The envelope byte estimate
must include rawData backing; an individual envelope larger than the total byte
limit is dropped immediately after its cost is returned rather than blocking or
escaping the bound.

### 4. Make the physical writer friendly to rotational disks

Use one serial writer per workspace. Multiple compression workers may prepare
independent candidate frames when CPU policy permits, but only one component should
create and publish history segments for a workspace. Parallel disk writers that
look attractive on SSDs commonly reduce HDD throughput by forcing head movement
between files and directories. The same single-writer contract applies to fast,
local, and distributed results and must not be selected by backend.

The writer should form a segment when the first of three bounded conditions is met:

- target encoded bytes, initially benchmarked in the 4--32 MiB range;
- maximum candidate count, initially benchmarked in the 32--256 range;
- maximum residence time, initially benchmarked in the 0.2--1.0 second range.

One reasonable starting profile for small SAW-like records is 4 MiB, 128
candidates, or 0.5 seconds, whichever comes first. These are benchmark starting
points, not immutable public constants. The byte and item bounds cap data loss;
the residence bound prevents a slow evaluator from leaving one candidate pending
indefinitely. Do not infer HDD versus SSD from fragile platform/model-name
heuristics. Prefer one portable sequential-write default and expose only bounded
common tuning when measured workloads justify it.

For each segment:

1. encode/compress every candidate independently in memory or bounded staging;
2. issue large buffered sequential writes into one same-directory temporary file;
3. write the segment footer/index last;
4. close and atomically rename the temporary file;
5. never modify, compact, or append to the published segment.

Do not call `fsync`/`FlushFileBuffers` for every candidate. The accepted durability
policy permits losing recent data after a power or machine failure, so the default
may rely on ordinary close plus atomic rename and operating-system writeback.
If an explicit stronger durability option is added, flush at most once per segment
or generation and keep it off the evaluator's synchronous path. Document clearly
that atomic rename prevents normal readers from accepting a half-published file but
does not by itself guarantee power-loss durability.

Avoid synchronous per-candidate index transactions, directory scans, and global
manifest updates. Update a disposable index in grouped transactions after segment
publication, checkpoint index state infrequently, and allow several new segments
to exist before indexing. Compression should reduce device bytes without making
the disk writer wait on an unbounded CPU pool; store already-compressed candidate
frames without a second whole-segment compression pass.

Do not run online compaction or rewrite old segments during an optimization. Such
work turns linear append traffic back into competing reads and writes and causes
severe seek amplification on one HDD. Any future compaction is an explicit offline
maintenance operation whose failure leaves the original immutable segments
untouched.

Optimizer-facing state should not rescan the records directory after every
candidate or generation. Load one tolerant history snapshot at run start, update
the current run's usable outcomes in memory, and let immutable segment discovery
or index refresh occur at bounded checkpoints. Full-history surrogate or viewer
reads should traverse a stable segment snapshot sequentially and must not hold the
writer lock. Where a background surrogate reads the same HDD while recording, its
I/O should be chunked/yielding or schedulable so one large scan cannot indefinitely
starve sequential publication; storage contention may reduce throughput but must
not propagate as campaign failure.

The 5,000-candidate SAW evidence provides a scale check. About 170 MB of useful
rawData plus metadata caused roughly 425 GB of logical archive/manifest rewriting;
the archive-copy portion also required reading the old bytes before writing the new
copy. Immutable segments should reduce authoritative publication to approximately
the newly encoded evidence plus small framing/index overhead--about 2,500 times
less logical rewrite work for that run. A typical HDD may then spend seconds to
tens of seconds on the history payload instead of tens of minutes or hours on
repeated same-volume copies. This is an order-of-magnitude expectation for design
and benchmark selection, not a promised wall-clock result: simulator scratch,
antivirus, compression CPU, filesystem cache, and concurrent readers still matter.

### 5. Treat indexes and summaries as disposable caches

An SQLite index may accelerate filtering by run, generation, status, or candidate,
but immutable segments and their valid candidate frames are the durable source when
publication succeeds.
The index must be deletable and reconstructible by scanning records. Index absence,
lock contention, transaction failure, schema mismatch, or corruption must not
invalidate candidate frames/segments or stop optimization.

The writer may update the cache after segment publication. If cache update fails,
keep the segment and mark/rebuild the cache later. Do not implement a two-resource
transaction that makes segment publication depend on SQLite. Avoid storing rawData
only as database BLOBs, which would recreate one central mutable failure domain.

Readers should use an index only when it is valid. They must fall back to a bounded,
diagnostic segment scan and may rebuild the cache asynchronously or on an explicit
maintenance path. Scan segment files in stable name order, read each segment
sequentially, and avoid one random open per candidate. Cache rebuild failure returns
the valid subset already found or an empty history; it does not abort a campaign.

### 6. Define tolerant read and recovery semantics

Every history consumer, including optimizer warm start, resource calibration,
surrogate training/recovery, cost/time views, history tools, and checkpoint
inspection, must share these rules:

- a malformed, truncated, checksum-invalid, or unreadable candidate frame is
  skipped individually when the segment directory remains trustworthy;
- a malformed/truncated segment header or footer may discard that complete bounded
  segment, but never any earlier segment or the running campaign;
- temporary files, unknown non-segment files, gaps in generation/population indices,
  missing candidates, and missing segments are accepted;
- duplicate identities are resolved by one deterministic rule and reported, not
  raised as a global error;
- incompatible task/static signatures are excluded without poisoning compatible
  records;
- an unreadable records directory or zero valid candidates yields an empty-history
  result plus bounded diagnostics;
- insufficient surrogate evidence skips training/use and falls back to the base
  real-evaluation optimizer path;
- incompatible or orphaned surrogate checkpoints are ignored rather than required
  for continuation;
- no query holds a lock that blocks candidate publication for the duration of a
  full-history cost or surrogate calculation.

User-invoked inspection commands may return a nonzero status when their explicit
purpose cannot be fulfilled, but an inspection failure must not mutate history or
leak into a running optimizer. The optimizer-facing history APIs must always offer
a non-throwing partial/empty recovery path for storage failures.

### 7. Remove old-format and backend-specific machinery

Backward compatibility is not required. Prefer a clean replacement over dual
writing, automatic migration, legacy aliases, or permanent fallback branches.

- Stop writing `recorded_data/rawData.npz` and `indMeta.jsonl`.
- Remove the single-versus-batch public distinction from evaluation orchestration.
- Remove the fast inline `record_result()` path and the local/distributed
  `record_results()` plus per-individual publication fallback.
- Remove old archive-copy, whole-JSONL-rewrite, and global-record-lock logic once no
  current reader/writer uses it.
- Put the new format below a distinct directory/version so old files cannot be
  mistaken for new records. A run may issue one bounded warning that legacy
  history is ignored; it must then continue as an empty/new-format history.
- Do not automatically delete or rewrite legacy user data. Destructive cleanup
  remains explicit and workspace-scoped.

Update history clearing, workspace checks, package documentation, and tools for the
new paths. Remove tests that exist only to preserve the old storage format; replace
them with tests of the new intent instead of layering compatibility onto the new
implementation.

### 8. Keep failure domains precise

Do not broaden “recording must not crash optimization” into hiding scientific or
execution errors:

- invalid task rawData, task cost errors, simulator crashes, and timeouts remain
  candidate evaluation failures with correct-width infinite costs;
- a persistence failure after a valid cost is a recording loss, not an evaluation
  failure;
- a recorder failure cannot cancel, time out, retry, or replace a backend worker;
- a backend worker failure cannot corrupt or stop the recorder;
- distributed submit/collection failure still follows distributed candidate
  failure semantics before the common finalizer;
- queue loss must be visible in bounded diagnostics even though it is non-fatal.

This separation must also correct timing semantics. Simulator/worker execution,
parent-side completion wait, cost calculation, queue admission, and asynchronous
record publication should have distinct measurements. Evaluation elapsed time and
timeout logic must not include time spent waiting for unrelated history I/O after
the backend result is available.

### 9. Suggested implementation sequence

1. Introduce the backend-neutral outcome/finalizer and direct-from-result current
   cost calculation while retaining temporary test adapters around old storage.
2. Implement the independently framed candidate codec, immutable micro-batch
   segment codec, atomic serial writer, tolerant sequential scanner, and optional
   disposable index.
3. Implement the bounded recorder supervisor, item/byte/time segmenter, owned
   envelope rules, loss counters, circuit breaker, and bounded shutdown.
4. Route fast, local, and distributed results through the common finalizer and
   recorder, then delete backend-specific publication branches.
5. Convert optimizer history, calibration, surrogate, viewers, history clearing,
   and metadata recording to the new tolerant query surface.
6. Delete the old history format and compatibility scaffolding, then update current
   architecture, blueprints, terminology, user documentation, and change records.

Intermediate stages must not claim the final reliability contract while a
recording exception can still propagate into a campaign or one backend retains a
different writer.

### 10. Verification and acceptance tests

Use deterministic failure injection in generic package tests. At minimum cover:

- fast, local, and mocked distributed results entering the same finalizer and the
  same writer API, with no direct backend persistence calls;
- equivalent file-backed and memory-backed rawData producing the same current
  costs and candidate-frame contents;
- a segment write that never reads, opens, copies, or modifies earlier segments;
- thousands of synthetic candidates without write work proportional to accumulated
  history size; prefer operation-count assertions and a generously bounded
  integration timing trend over a fragile microbenchmark alone;
- one serial workspace writer, with instrumented assertions that concurrent backend
  completions cannot produce competing segment writes;
- deterministic byte/count/time segment flush behavior, including the configured
  maximum loss domain and a low-rate evaluator reaching the residence deadline;
- independently corrupting one candidate frame inside a valid multi-candidate
  segment and retaining valid siblings; corrupting/truncating a segment footer must
  skip at most that segment and allow optimization/history recovery to continue;
- instrumented HDD-shape tests that bound segment/file creation, directory updates,
  flushes, index transactions, and seeks/opens by segment count rather than
  candidate or historical-record count;
- a sequential-throughput integration profile using small SAW-like payloads and a
  deliberately slow/seek-penalized filesystem double; the result should favor
  micro-batch segments over per-candidate files without requiring a physical HDD in
  the default suite;
- no per-candidate durability flush, index transaction, or history-directory scan;
  an optional stronger flush policy, if present, is bounded to segment/generation
  granularity and remains asynchronous;
- queue-full behavior, byte-limit behavior, and an oversized single record being
  dropped without blocking or changing its optimizer cost;
- permission denied, disk-full simulation, temporary-file creation failure,
  encoding failure, atomic-replace failure, index lock/corruption, and recorder
  thread/process death while later candidates and generations continue;
- abrupt termination leaving a temporary segment that the next run ignores;
- one corrupt finalized candidate frame among valid siblings, returning all valid
  history and bounded diagnostics;
- missing records, generation gaps, duplicate identities, incompatible signatures,
  and completely unreadable/empty history;
- surrogate fallback and optimizer cold start when too little valid history
  remains;
- bounded recorder shutdown when a writer is blocked, including explicit accounting
  of discarded queued envelopes;
- progress and strict all-infinite behavior depending on evaluation/cost results,
  not on recording success;
- isolation of simultaneous workspaces and absence of a package-global recorder or
  index path;
- artifact, read-only-site-packages, CLI, history-view, and clear-history contracts
  for the new format.

Include a regression based on the SAW failure shape or an equivalent synthetic
small-result workload: actual evaluation throughput must not show a linear trend
with the number of already persisted candidates, and scheduler-observed evaluation
time must not absorb asynchronous record publication latency.

## Non-Goals

- Guaranteeing that every successful candidate becomes durable.
- Providing a generation-level durability barrier before optimization continues.
- Recovering queued-but-unpublished records after process or machine loss.
- Making the candidate store transactional as a whole campaign.
- Guaranteeing power-loss durability for an atomically renamed but unflushed
  segment, or flushing every candidate to obtain that guarantee.
- Automatically detecting storage media type or maintaining separate backend-
  specific HDD/SSD writers.
- Performing online segment compaction during optimization.
- Preserving or automatically migrating the current JSONL/global-ZIP format.
- Treating stored cost snapshots as authoritative after task cost policy changes.
- Retrying indefinitely, allowing an unbounded queue, or blocking simulator
  scheduling until storage recovers.
- Hiding simulator, task, rawData-validation, or cost-calculation failures as though
  they were harmless recording loss.

## Completion Rule

This toDo is complete only when all of the following are true:

- fast, local, and distributed evaluation share one backend-neutral finalizer,
  candidate-envelope contract, and immutable micro-batch segment writer;
- current costs are calculated before and independently of durable publication;
- the running optimizer continues through every injected recording, index, and
  partial-history failure described above;
- the writer has bounded item/byte capacity, bounded failure/retry behavior, and a
  bounded shutdown path that may explicitly lose records;
- no authoritative campaign-wide individual manifest or rawData archive is copied,
  rewritten, or required for new-format recovery, and published segments are never
  mutated or compacted during optimization;
- one workspace-scoped serial writer performs bounded byte/count/time micro-batching
  and sequential segment publication without per-candidate flush/index/scan work;
- candidate frames remain individually checksummed and recoverable within a valid
  segment, while a completely bad segment is a bounded non-fatal loss domain;
- history, optimizer, calibration, surrogate, and inspection consumers isolate bad
  candidates and support partial or empty history according to their runtime role;
- the old format and backend-specific recording paths are removed rather than kept
  as compatibility layers;
- current architecture, blueprints, terminology, user documentation, and generic
  tests describe and enforce the new durability and loss semantics;
- a large synthetic regression demonstrates write work independent of accumulated
  history and no linear evaluation-time slowdown.

After implementation and documentation are complete, move this one-shot manual
toDo to `dev_doc/obsolete/` according to the documentation contract.
