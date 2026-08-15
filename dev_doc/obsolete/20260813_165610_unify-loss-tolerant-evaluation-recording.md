# Unify Hot-Reloadable, Loss-Tolerant Evaluation Recording

## Status And Scope

This is a manual future-work specification. Reading it does not authorize an
implementation. It replaces the earlier design of the same name; the complete
pre-revision document is preserved at
`dev_doc/obsolete/20260813_165610_unify-loss-tolerant-evaluation-recording.md`.

The work may make large incompatible changes. The current global
`recorded_data/rawData.npz` and `indMeta.jsonl` format does not need a
compatibility reader, automatic migration, or dual-write period.
The segment implementation does not inspect those legacy files: if they happen to be
present, it starts with empty segmented history and leaves every legacy file untouched.
The user is responsible for not mixing old-format and segmented campaigns in one
workspace.

The expected campaign scale for this design is normally several tens of thousands
of candidates and is not expected to exceed 100,000 in the foreseeable future.
The implementation should remain structurally linear, but it must not add database
or distributed-storage machinery solely for hypothetical million-candidate use.

## Background

### Observed fast-mode slowdown

Yadof intends fast, local, and distributed evaluation to differ only in execution
transport. After a backend produces rawData and diagnostics, validation, current
cost calculation, population ordering, failure isolation, and best-effort recording
should have one meaning.

The current implementation violates that intent:

- local and distributed normally collect a population and call the batch
  `record_results()` path;
- fast calls single-result `record_result()` synchronously from each worker
  completion callback;
- both paths mutate one campaign-wide rawData ZIP and rewrite campaign-wide JSONL;
- cost return reopens recorded history instead of calculating directly from the
  already available result.

For one single-result publication, the existing recorder reads the growing
manifest, copies the complete growing rawData archive, appends one candidate,
rewrites the manifest, and atomically replaces both files. The cost of recording
candidate N is therefore proportional to all earlier history, not to candidate N's
new evidence. Batch recording reduces how often this occurs but does not remove
the campaign-size dependency.

Fast mode amplifies the defect because its completion callback performs that
synchronous publication before releasing the worker slot or draining other
completed worker pipes. Other workers can be finished yet wait behind parent-side
history I/O. Their scheduler-observed elapsed time then looks like simulation time
even though the simulator itself stayed fast.

### Reproduction evidence

The `20260807 saw` workspace recorded 5,000 candidates over 50 generations:

| Measurement | Generation 0 | Generation 49 |
|---|---:|---:|
| Mean ngspice simulation time | 0.091 s | 0.080 s |
| Mean fast worker time | 0.106 s | 0.094 s |
| Mean recorded individual `elapsed_time` | 0.505 s | 5.755 s |
| Whole-generation wall time | 13.728 s | 166.624 s |

Generation wall time fit approximately
`15.437 + 3.062 * generation_index` seconds with `R^2 = 0.9973`, while
ngspice time stayed flat or improved. The final useful history was only about
170 MB, but the algorithm performed an estimated 369.6 GB of logical rawData
archive copying plus 55.2 GB of logical manifest rewriting. These figures are
algorithmic byte estimates, not physical-drive SMART measurements; they still
demonstrate the quadratic rewrite shape.

The same history contained three successful evaluations that became recording
errors after Windows denied a manifest temporary-file replacement. No fast scratch
leak, descendant-process leak, or simulator-time growth was found.

### Why HDD behavior affects the design

Removing whole-history copying is the dominant improvement on every storage
device. Mechanical disks add three constraints:

- many per-candidate files cause directory updates, small writes, and seeks;
- multiple disk writers can reduce throughput by moving the head between streams;
- per-candidate durability flushes can add a rotation wait to every result.

Therefore the physical writer should use one workspace-scoped serial stream and
publish small immutable batches through large buffered sequential writes. The
logical unit remains one candidate, but the normal filesystem unit is a bounded
segment containing several candidates. This HDD requirement justifies
micro-batching; it does not by itself justify a new custom binary container,
multiple compression workers, or a database.

### Flexibility and live task correction are core behavior

Yadof deliberately lets a user edit `calc_cost.py`, parameter definitions,
configuration, `workflow.py`, `evaluation.py`, and task helpers while a campaign
is running. A common reason is that the user discovers an error in the optimization
problem after expensive evaluations already exist and wants to correct it without
restarting the process or being forced to discard all compatible evidence.

The corrected optimization problem is expected to be different. Yadof must not ask
whether the old and new problems are “scientifically equivalent”, infer whether the
change was scientifically wise, or use a hash mismatch as a reason to reject
otherwise mechanically interpretable evidence. Scientific suitability is a user
decision. Yadof trusts the user to decide whether old evidence should remain,
whether history should be cleared, or whether a separate workspace should be used.

For this document, **mechanically interpretable** has a narrower software meaning:
the current parameter and cost code can load a record, normalize its stored raw
variables, read its rawData schema, and produce the current objective tuple. A
record that lacks a newly required variable or contains rawData the new cost code
cannot read may be skipped with diagnostics. That is an actual processing failure,
not a scientific-equivalence judgment.

Hot changes take effect at the next generation boundary. One generation uses one
coherent task/config snapshot; yadof must not let candidates within the same
generation silently mix pre-edit and post-edit definitions. At the next boundary
parameter normalization, current cost interpretation, evaluator behavior, and the
derived history view are rebuilt from current workspace code.

This recording project assumes that parameter identity/count and objective count
stay fixed for the campaign. Users may correct parameter ranges or levels, cost
logic and thresholds, configuration, workflow/evaluation code, and task helpers,
but they are responsible for preserving the parameter schema and objective width.
Supporting parameter add/remove/rename operations or objective-width changes
requires separate optimizer-state semantics and belongs in a future toDo.

## Locked Product Decisions

The implementation must preserve these decisions:

1. Fast, local, and distributed share one backend-neutral finalizer and one
   recording implementation.
2. Current cost is calculated from the completed result before and independently
   of durable publication.
3. History persistence is best effort. A persistence failure after valid rawData
   and cost is recording loss, not an evaluation failure.
4. One independent background writer thread keeps disk publication off the
   evaluation scheduling path.
5. Recording loss should be as small as practical and must remain bounded by the
   selected runtime limits. Initial 16-candidate segment and 32-candidate total
   unpublished limits are tuning defaults, not a product boundary where one more
   lost candidate suddenly becomes unacceptable. Generation is not a persistence
   transaction or intentional batching unit, but systemic storage/process failure
   may still lose a complete generation.
6. The loss bound counts every unpublished candidate: assembling, queued, encoding,
   temporary-file, and in-flight publication states.
7. One workspace has at most one active optimization campaign. Concurrent
   campaigns use different workspaces.
8. Task and task-semantic configuration edits remain supported between generations
   while parameter identity/count and objective count stay fixed. Yadof does not
   judge scientific compatibility and does not silently freeze a campaign's
   original task.
9. The design targets at most 100,000 candidates. SQLite and custom segment
   protocols require measured evidence before they enter the implementation.
10. Old history-format compatibility or detection is not required. Segment storage ignores old
    files, starts cold, and never deletes or rewrites them.
11. Recorder infrastructure configuration, including history paths, segment/queue
    budgets, writer failure policy, and shutdown policy, is frozen when the
    campaign starts. Changing those settings takes effect only for a later
    campaign/process.

## Goal

Implement this pipeline:

```text
generation controller
  -> load one current config/task snapshot
  -> fast/local/distributed backend
  -> backend-neutral JobResult
  -> common validation + current cost finalizer
  -> finalized JobResult returned to optimizer immediately
  -> non-blocking owned-envelope admission
  -> one workspace background writer thread
  -> immutable standard-ZIP micro-batch segment
```

When complete:

- new publication work is proportional to newly admitted bytes and never rewrites
  older segments;
- worker release and result-pipe draining never wait for history I/O;
- a finite candidate cost stays finite when its record is dropped or cannot be
  written;
- recording loss, corrupt segments, unreadable history, and a dead writer cannot
  terminate the campaign;
- shape-preserving task edits are observed coherently at generation boundaries and
  cause current history reinterpretation without a scientific-equivalence gate;
- bad or mechanically incompatible records are isolated, while valid records and
  later generations remain usable;
- HDD file creation, directory updates, seeks, and flushes scale with segment count,
  not candidate count or total prior history.

This guarantee is scoped to catchable history-persistence and history-reading
failures after a backend has produced a result. It cannot promise continuation
after process termination, interpreter failure, OOM, arbitrary filesystem failure
affecting task inputs or simulator scratch, or machine loss.

## Detailed Design Intent

### 1. Use a generation-scoped task snapshot

At the start of every generation:

1. reload generation-scoped task/evaluation/optimizer configuration while retaining
   the campaign-start recorder infrastructure configuration;
2. fresh-load current parameters with the campaign's stable identities/count,
   current objective names with the stable objective count, cost code, evaluator,
   and task helpers through the normal isolated task loader;
3. calculate component fingerprints plus one complete task-snapshot identity;
4. retain the optimizer dimensional structure and apply current shape-preserving
   task definitions;
5. reinterpret the usable history view only when its interpretation fingerprint
   changed.

Do not use one monolithic fingerprint as every cache key. Maintain at least:

- an `interpretation_fingerprint` covering parameter ranges/levels, objective
  naming/cost code, and helpers used to normalize evidence or calculate cost;
- an `evaluation_fingerprint` covering workflow/evaluation code and execution-side
  helpers, used as provenance for newly produced evidence rather than as a reason
  to recalculate unchanged historical costs;
- a complete `task_snapshot_id` identifying the coherent combination used by one
  generation for diagnostics and provenance.

These fingerprints are not scientific signatures. Their purposes are to notice
that particular derived values may be stale, invalidate only the affected caches,
and explain which source snapshot produced evidence or diagnostics. A changed
fingerprint must not automatically exclude old records. Every old record is
attempted under current shape-preserving definitions:

- changed parameter ranges renormalize stored raw values;
- parameter names and count remain fixed for this project;
- changed `calc_cost.py` recalculates current costs from compatible rawData;
- changed objective definitions or names retain the existing objective count;
- changed workflow/evaluation code affects future evidence at the next generation;
- old rawData remains eligible when current code can interpret it.

The user, not yadof, decides whether combining old and new evidence is scientifically
appropriate. History clear and using a new workspace remain explicit user choices.

Do not reload task files independently for each candidate in a way that permits a
mid-generation edit to split one population across definitions. Local/distributed
prepared jobs and fast worker requests must identify the same generation snapshot.
Materialize or content-address the relevant configuration and Python task-source
bytes at generation start; calculating a fingerprint and then continuing to import
mutable live files is not a coherent snapshot. Large task-owned simulator assets
need not be duplicated merely for this mechanism, but users who replace such assets
must use a stopped generation boundary or a separate workspace.

Recorder infrastructure is not part of this hot reload. The active writer keeps
the history root, lock identity, count/byte limits, segment policy, failure policy,
and shutdown deadline captured at campaign start. Later edits to those settings do
not redirect or resize an existing writer.

### 2. Reuse the existing result model

`JobResult` already carries identity, status, raw variables, diagnostics, rawData
backing, and optional costs. Prefer completing that object, for example with
`dataclasses.replace()`, or using a thin internal finalizer return. Do not add a
second public `EvaluationOutcome` model unless implementation evidence finds a
semantic invariant that `JobResult` cannot express.

The common finalizer must:

1. validate the backend-neutral rawData source;
2. load it once into canonical owned `RawDataItem`-equivalent values;
3. calculate current costs using the generation snapshot, without opening durable
   history;
4. return the finalized ordered result to progress/optimizer control;
5. offer an owned record envelope to the recorder through a non-blocking call.

Invalid rawData and current-cost errors remain evaluation failures with the current
objective-width `inf` sentinel. Queue refusal or later persistence error must not
change a successful cost, strict all-infinite handling, or worker lifecycle.

### 3. Give the recorder owned data, not borrowed paths

The finalizer should reuse the rawData load already needed for validation and cost.
Fast memory payloads and local/distributed files converge to one owned envelope
before admission. The background writer must not depend on a job path remaining
alive after the evaluator returns.

The envelope contains:

- stable candidate/run/optimization/generation/population identities;
- raw variables as a name/value mapping, not only a positional tuple, plus the
  generation source fingerprint;
- status, timestamps, execution provenance, and bounded diagnostics;
- every validated rawData item needed for future reinterpretation;
- optional current objective names/costs as a derived diagnostic cache, tagged with
  the interpretation fingerprint that produced them.

Stored costs are never source truth. A reader may reuse them only as a derived cache
when the current interpretation fingerprint exactly matches; otherwise it
recalculates from rawData. The format and reader must work when this optional cache
is absent, so cache persistence can be deferred if first-version benchmarks do not
justify it.

Admission accounts conservatively for peak resident ownership, not merely the
eventual compressed member size. The reservation must cover source arrays,
metadata, encoding buffers or temporary files, and any overlap while ownership is
transferred or released. Do not copy or serialize the same payload repeatedly
merely to move it between finalizer, queue, and writer.

A representative large yadof result is an antenna pattern containing
`10 * 360 * 360 = 1,296,000` floating-point values. Its main array alone is about
4.94 MiB as float32 or 9.89 MiB as float64 before axes, metadata, other rawData
items, and encoding overhead. Default byte limits must be benchmarked against both
small SAW-like candidates and at least this large-payload shape. The normal segment
byte target must not double as the maximum legal candidate size.

### 4. Use one bounded background writer thread

Create one writer thread for one active campaign in one workspace. Use a daemon
thread so a permanently blocked filesystem call cannot keep a command-line process
alive forever. Do not create one writer per backend, worker, generation, or
segment.

Initial loss/throughput profile:

- candidate-count segment target/default limit: 16;
- total unpublished candidate default limit: 32;
- normal segment byte target: benchmark an initial 8--16 MiB value against both
  small and large tasks rather than treating the SAW payload size as representative
  of all yadof tasks;
- separate maximum single-candidate reservation and total unpublished byte limits,
  chosen so the default admits at least the representative antenna payload above;
- flush a partial segment at population/generation/evaluation-call boundaries;
- no residence-time timer is required for generation-based calls.

The count values above are initial defaults and the implementation may expose them
as advanced configuration. Every campaign freezes and enforces the selected values,
but product correctness does not depend on 16 or 32 being universally special.
Count and byte limits remain independent because small candidates stress file/seek
shape while large candidates stress memory and I/O volume.

The byte target is a normal flush threshold, not a hard per-candidate rejection
threshold. A candidate that exceeds the target but fits the maximum
single-candidate reservation is published as a singleton segment. A candidate that
exceeds the maximum single-candidate reservation or cannot fit the total
unpublished byte budget is dropped only after its current cost has been returned.

The unpublished budget includes candidates being assembled, waiting in the queue,
encoded into a temporary file, and actively written but not atomically published.
Credits are released only after publication succeeds or the data is explicitly
dropped. This keeps abrupt-process-loss exposure within the campaign's configured
candidate and byte budgets. One failed or corrupt segment normally loses no more
than that segment's configured candidate/byte limits. Yadof minimizes this exposure
but does not promise that systemic storage failure, writer disablement, or process
loss can never remove a complete generation.

Admission is non-blocking. When either budget is exhausted:

- drop the new envelope;
- increment an in-memory counter;
- issue a rate-limited warning;
- return to evaluation immediately.

The writer catches segment creation, encoding, permission, disk-full, close, and
atomic-replace failures. It drops only the affected segment and continues with
later admitted data. A successful publication resets the consecutive-failure
count. After a small documented number of consecutive systemic failures, disable
recording for the rest of that campaign and drop later offers. Do not build an
automatic restart service, cooldown scheduler, or unbounded retry loop.

If the writer thread dies unexpectedly, future admissions detect the state,
disable recording for that campaign, and keep optimization running. Normal shutdown
requests a flush and joins only for a bounded deadline. The deadline bounds how long
the optimization caller waits for best-effort history after evaluation has already
finished; it does not claim that Python can cancel a thread blocked inside an OS
filesystem call.

If the deadline expires, queued or assembling envelopes that have not entered the
blocking operation may be released and counted as shutdown-dropped. An in-flight
segment whose thread has not returned has an unknown outcome, not a proven drop,
because the call may later complete and publish it. A normal CLI command may then
return and its process may exit without the daemon writer keeping it alive.

For a long-lived Python process, a timed-out writer retains the workspace campaign
lock until the thread actually exits or the process ends. Later same-workspace
campaign or destructive-history calls fail fast during that interval. This is an
edge-case safety rule for notebook/service/API embedding, not the normal CLI flow
where each finite run/resume command owns one process. The shutdown timeout is
therefore a bound on caller/process-exit latency, not a promise of immediate
same-process workspace reuse.

Expose bounded counters such as offered, admitted, published candidates/segments,
queue-dropped, oversized-dropped, write-failed, disabled-dropped, and
shutdown-dropped, plus an in-flight-shutdown-unknown indicator. Logging failure is
itself non-fatal.

### 5. Publish immutable standard-ZIP segments

Use a versioned layout such as:

```text
recorded_data/
  segments/
    <run-id>/
        generation_000000/
          segment_000000.zip
          segment_000001.zip
    metadata/
      <immutable generation/run event files>
```

Each segment is a normal ZIP containing:

- one versioned manifest with candidate identities, metadata, member names, sizes,
  interpretation/evaluation fingerprints, and the complete task snapshot identity;
- candidate-scoped metadata members;
- candidate-scoped NPZ rawData members.

NPZ payloads are already compressed where appropriate. Prefer `ZIP_STORED` for
those members rather than performing a second whole-segment compression pass.
Small JSON members may use ordinary bounded compression if benchmarks justify it.

Write one same-directory temporary ZIP through large buffered sequential writes,
close it, then atomically rename it. Published segments are never reopened for
append, compaction, index repair, or metadata updates. The default does not call
`fsync`/`FlushFileBuffers`; process or power loss may lose the recent bounded
budget. Atomic rename prevents normal readers from accepting a half-published
temporary file but is not a power-loss durability guarantee.

Use ZIP member CRC and manifest size/member mapping instead of inventing a
length-delimited `.yadseg` frame protocol. If one candidate member fails CRC or
is missing, skip that candidate and keep valid siblings when the ZIP directory is
readable. If the central directory or manifest is unusable, skip the complete
segment; the campaign's configured segment limits define that bounded failure unit.

Run/generation/surrogate metadata must also avoid one growing mutable JSONL. Publish
small immutable event files or include the authoritative metadata in segment
manifests. Derived summaries may be rebuilt and are never required for recovery.

### 6. Keep current history hot without freezing task meaning

At campaign start, discover a stable snapshot of finalized segment names once and
build an in-memory catalog. Do not rescan the complete records tree after every
candidate or unchanged generation.

Keep this state private to an explicit campaign/session object; do not turn the
general recorded-data layer into a process-global in-memory database or registry.
The session owns its startup durable rows, lightweight finalized rows from the
current process, and the bounded recent pending/publication state needed by the
writer. Only rows still inside the recorder ownership window retain rawData in
memory.

Maintain a derived in-memory history view containing raw-variable coordinates,
current costs, provenance, and references to published segment evidence. Current
generation results may enter that view immediately so the optimizer need not wait
for persistence. Retain an unpublished result's rawData only while it remains in
the bounded recorder ownership window.

Track whether each in-process row is backed by a finalized segment, still owns a
pending envelope, or has been dropped. Publication replaces pending ownership with
a segment reference. A dropped row may remain usable from its already derived
variables/costs while the interpretation fingerprint is unchanged, but it has no
recoverable evidence: remove it from the derived history when a later task change
requires reinterpretation, and expect it to be absent after process restart.

When the interpretation fingerprint is unchanged, append new derived rows and
reuse the existing view. An evaluation-only fingerprint change records new
provenance but does not by itself rebuild old normalized variables or costs. When
interpretation-relevant task sources change:

1. invalidate derived normalization/cost caches;
2. take a stable snapshot of all finalized segments plus still-owned envelopes;
3. sequentially load candidate evidence and apply the new generation snapshot;
4. omit records that are missing, lost, corrupt, or mechanically uninterpretable;
5. update the derived history and next optimizer context without changing parameter
   identity/count or objective width.

This re-interpretation can create a one-time pause after an intentional task edit.
That cost is required by the flexibility contract and must be measured separately
from simulator and recorder timing. It must not become an every-generation disk
scan when source content is unchanged.

If a record was deliberately dropped and its rawData ownership has ended, it is
absent from future history. That is accepted data loss. It must never crash resume
or force the optimizer to wait for nonexistent durability.

### 7. Do not add SQLite in the first implementation

For the stated sub-100,000-candidate horizon, immutable segment discovery, compact
per-segment manifests, and one in-memory catalog are the first implementation.
Measure cold-start scan and viewer latency using the expected upper scale.

Add a rebuildable SQLite index only in a later measured change if startup or
interactive queries miss an explicit performance target. If introduced later, it
remains a disposable cache: segment publication never depends on an index
transaction, rawData is never stored only as BLOBs, and index failure cannot stop a
campaign.

### 8. Enforce one active campaign per workspace

Acquire an OS-backed workspace campaign lock for the lifetime of
`run_generations()` or the equivalent active optimization session. Two
optimizations must not write, reinterpret, or clear the same workspace
concurrently. A second optimization request fails early with an actionable message
directing the user to create another workspace.

Different workspaces retain independent locks, writers, queues, histories, and
surrogate state and may run concurrently.

Read-only viewers may inspect finalized immutable segments without taking the
campaign writer lock. `history clear` and other destructive history operations
must refuse while that workspace has an active campaign. Use an OS lock rather
than trusting a stale marker file after a process crash.

### 9. Share tolerant reader semantics

Optimizer warm start, resource calibration, surrogate training/recovery, history
tools, cost/time views, and checkpoint inspection must use one tolerant query
surface:

- ignore temporary and unknown files;
- skip an unreadable ZIP as one bounded segment loss;
- skip a candidate with missing/CRC-invalid/malformed members;
- accept gaps in generation and population indices;
- resolve duplicate candidate identities deterministically and report them;
- return a partial or empty history for storage/read failures;
- skip surrogate training/use when too little compatible evidence remains and fall
  back to real evaluation;
- never hold a long-lived reader lock that blocks atomic segment publication.

Do not exclude a candidate merely because its stored fingerprint differs from the
current generation. Fingerprints trigger recalculation. Only concrete current
normalization/rawData/cost failures make a record mechanically unusable.

Legacy global-ZIP/JSONL paths are outside this query surface. Their presence does
not trigger migration, confirmation, deletion, or an error; segment discovery behaves
as if they do not exist.

An explicitly invoked viewer may return a nonzero status when it cannot satisfy its
inspection request. That user-facing error must not mutate history or propagate
into a running optimizer.

### 10. Keep timing and failure domains precise

Measure separately:

- backend/simulator execution;
- parent completion-pipe wait;
- rawData validation and current cost;
- recorder admission;
- asynchronous segment encoding/publication;
- task-change history reinterpretation.

Evaluation elapsed time and timeout logic stop when the backend result is available;
they do not absorb unrelated history publication.

Scientific and execution failures remain normal candidate failures:

- simulator crash or timeout;
- distributed submit/collection failure;
- invalid task rawData;
- current `calc_cost.py` failure.

Recording failures after a valid cost are non-fatal recording loss:

- queue or byte-budget refusal;
- segment encoding/write/rename failure;
- exhausted history volume;
- corrupt/missing stored segment;
- writer disablement or death;
- index/cache failure if a cache is later added.

The persistence guarantee does not hide failures in task source files, job
preparation, simulator scratch, the Python process, or shared machine resources.

## Implementation Sequence

1. Add tests for generation-boundary shape-preserving task/config reload, changed
   parameter ranges, current-cost reinterpretation, the fixed parameter/objective
   dimensions assumed by this project, and the rule that component fingerprints
   invalidate only their affected caches without making scientific compatibility
   decisions.
2. Refactor the existing `JobResult` finalization so all backends calculate cost
   directly from one owned validation load. Temporary old-store adapters may remain
   only during this stage.
3. Implement the standard-ZIP segment encoder/scanner and immutable run/generation
   metadata events. Verify that new writes never open older segments.
4. Implement the single bounded background thread, complete unpublished-budget
   accounting, non-blocking admission, failure disablement, and bounded shutdown.
5. Route fast, local, and distributed through the common finalizer/recorder and
   remove fast inline recording plus local/distributed batch/fallback policy.
6. Implement the campaign-owned derived-history state and component-fingerprint
   invalidation/reinterpretation behavior.
7. Convert optimizer, resource calibration, surrogate, viewers, history clear, and
   workspace checks to the tolerant segment query surface and campaign lock.
8. Delete old global ZIP/JSONL readers, writers, locks, and compatibility tests.
9. Update current architecture, blueprints, terminology, user documentation, and
   generic tests; then archive this one-shot toDo.

Intermediate commits must not claim final reliability while one backend still has
a different persistence policy or a recording exception can propagate into
optimization.

## Verification And Acceptance

### Common finalization and hot reload

- Fast, local, and mocked distributed results enter the same finalizer and recorder
  offer API.
- File-backed and memory-backed evidence produce equal finalized costs and equal
  logical record content.
- The finalizer reuses `JobResult`; any new result type must be justified by a
  tested semantic distinction.
- Editing `calc_cost.py` between generations recalculates old compatible rawData
  and affects the next generation.
- Editing parameter ranges/levels renormalizes stored raw variables while parameter
  identity/count remains fixed.
- Editing objective definitions or names affects the next generation while the
  objective count remains fixed.
- Editing workflow/evaluation/task helper code affects the next generation and
  does not split the current generation across source snapshots.
- A changed fingerprint never excludes a record by itself; an evaluation-only
  fingerprint change does not recalculate unchanged historical costs.
- An unchanged interpretation fingerprint does not cause a full segment-tree scan
  or full cost recalculation every generation.
- Editing recorder infrastructure configuration during a campaign does not redirect
  or resize the already running writer.

### Bounded asynchronous loss

- The selected campaign configuration, including the initial 16-candidate segment
  and 32-candidate unpublished defaults, is enforced exactly but is tested through
  parameterized limits rather than treated as a universal acceptability boundary.
- Instrumentation proves that assembling + queued + encoding + temporary +
  in-flight candidates and their resident/encoding reservations never exceed the
  selected count or total byte budgets.
- A candidate larger than the normal segment byte target but within the maximum
  single-candidate reservation publishes as a singleton segment.
- Queue/byte exhaustion and a candidate above the real single-candidate hard limit
  drop immediately without changing the returned cost or delaying worker release.
- Segment errors lose at most that segment; later admitted segments can publish.
- Consecutive systemic failures disable recording without stopping later
  generations.
- Unexpected writer death disables recording without an automatic restart loop and
  without terminating optimization.
- Bounded shutdown releases candidates that have not entered a blocked I/O call,
  reports an in-flight unknown outcome when necessary, and never claims to cancel a
  blocked Python thread.
- A timed-out writer cannot keep a CLI process alive; a long-lived embedding retains
  the workspace lock and rejects later same-workspace mutation until that thread
  actually exits or the process ends.

### Format, HDD shape, and recovery

- A segment write never reads, opens, copies, appends, or modifies an earlier
  segment.
- Temporary files are ignored after abrupt termination.
- Corrupting one candidate member skips that candidate while readable siblings
  survive; corrupting the ZIP directory skips at most one configured segment.
- No per-candidate filesystem file, `fsync`, index transaction, global manifest
  rewrite, or history-directory scan exists in the hot write path.
- Instrumented tests prove that a new publication opens no old segment, writes bytes
  proportional to new evidence, and performs file creation, rename, directory
  update, and durability flushes only per segment. Per-member ZIP operations may
  have a documented constant factor bounded by the configured candidates per
  segment.
- An operation-count test plus a broad seek-penalized integration model favors
  sequential micro-batches over per-candidate files without requiring a physical
  HDD or asserting implementation-specific exact seek counts.
- Missing segments, duplicate identities, generation gaps, permission errors,
  disk-full errors, atomic-replace failures, and empty history return a valid
  partial/cold-start result.

### Campaign and scale behavior

- A second campaign in one workspace fails before evaluation; campaigns in two
  workspaces run independently.
- History clear refuses while the target workspace campaign lock is held.
- Surrogate insufficiency or incompatible checkpoints fall back to base real
  evaluation.
- A synthetic 5,000-candidate SAW-shaped regression has no evaluation-time trend
  proportional to already persisted candidates.
- A large-payload regression includes a `10 * 360 * 360` float32 and float64 main
  array, verifies singleton publication above the normal segment target, and
  measures peak reservation/encoding memory rather than only final compressed size.
- A synthetic upper-scale catalog near 100,000 candidates measures cold-start and
  reinterpretation costs without requiring SQLite. Record the result so a later
  index decision is evidence-based.
- Progress and strict all-infinite behavior depend on execution/current-cost
  results, never on record publication success.

Prefer operation-count assertions and broad trend bounds over fragile
millisecond-level benchmarks.

## Non-Goals

- Guaranteeing that every successful candidate becomes durable.
- Making one generation a durability transaction or normal loss unit.
- Guaranteeing that a systemic writer/storage/process failure can never lose a
  complete generation; the design only bounds and minimizes best-effort loss.
- Recovering queued but unpublished data after process/machine loss.
- Guaranteeing power-loss durability or flushing every candidate.
- Automatically deciding whether a user's task change is scientifically correct.
- Freezing task definitions for a campaign.
- Supporting parameter add/remove/rename operations, parameter-count changes, or
  objective-count changes during a campaign. This needs separate optimizer-state
  semantics and a future toDo; this project assumes stable parameter identity/count
  and objective width.
- Preserving or migrating the old JSONL/global-ZIP format.
- A custom `.yadseg` framing/footer/salvage protocol in the first implementation.
- SQLite in the first implementation.
- Multiple compression or disk-writer workers for one workspace.
- Automatic writer restart, indefinite retries, or unbounded queues.
- Online compaction or rewriting published segments.
- Automatic HDD/SSD detection or backend-specific storage implementations.
- Concurrent optimization campaigns inside one workspace.
- Optimizing for more than 100,000 candidates without new measured requirements.
- Hiding simulator, task, rawData, cost, process, or non-history filesystem
  failures as harmless recording loss.

## Completion Rule

This toDo is complete only when:

- all evaluation backends share the same `JobResult` finalizer, owned envelope,
  non-blocking recorder offer, and standard-ZIP segment writer;
- current cost is available before and independently of persistence;
- one background writer thread per active workspace campaign publishes immutable
  segments and never rewrites prior history;
- one segment and the complete unpublished state are proven to remain within their
  campaign-selected count and peak-resident byte budgets, with 16/32 retained only
  as initial defaults;
- every injected catchable recording/read failure leaves optimization able to
  continue;
- generation-boundary shape-preserving edits to cost, parameter ranges/levels,
  objective definitions, evaluator/task code, and task-semantic config are
  supported without a scientific-equivalence gate, while recorder infrastructure
  remains campaign-frozen;
- one active campaign per workspace is enforced and documented;
- tolerant readers, cold start, surrogate fallback, viewers, clear-history, and
  resume use the new segment contract;
- old format and backend-specific persistence branches are removed;
- tests demonstrate HDD-shaped sequential I/O, sub-100,000-candidate scale, and no
  history-size-dependent evaluation slowdown;
- current architecture, blueprints, terminology, user documentation, and one
  change record agree with the implemented behavior.

After implementation is fully complete, move this manual toDo to
`dev_doc/obsolete/` according to the documentation contract.
