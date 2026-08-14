# Unify Hot-Reloadable, Loss-Tolerant Evaluation Recording

## Status And Scope

This is a manual future-work specification. Reading it does not authorize an
implementation. It replaces the earlier design of the same name; the complete
pre-revision document is preserved at
`dev_doc/obsolete/20260813_165610_unify-loss-tolerant-evaluation-recording.md`.

The work may make large incompatible changes. The current global
`recorded_data/rawData.npz` and `indMeta.jsonl` format does not need a
compatibility reader, automatic migration, or dual-write period.

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
the optimizer problem, parameter normalization, objective names/count, evaluator,
and derived history view are rebuilt from current workspace code.

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
5. It is acceptable to lose a bounded batch of 16 or 32 candidates. It is not
   acceptable to make a whole generation the normal loss unit.
6. The loss bound counts every unpublished candidate: assembling, queued, encoding,
   temporary-file, and in-flight publication states.
7. One workspace has at most one active optimization campaign. Concurrent
   campaigns use different workspaces.
8. Task and configuration edits remain supported between generations. Yadof does
   not judge scientific compatibility and does not silently freeze a campaign's
   original task.
9. The design targets at most 100,000 candidates. SQLite and custom segment
   protocols require measured evidence before they enter the implementation.
10. Old history-format compatibility is not required.

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
- task edits are observed coherently at generation boundaries and cause current
  history reinterpretation without a scientific-equivalence gate;
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

1. reload effective workspace configuration;
2. fresh-load current parameters, objective names/count, cost code, evaluator, and
   task helpers through the normal isolated task loader;
3. calculate a content fingerprint for cache invalidation and provenance;
4. build a new optimizer problem/context from the current variable and objective
   counts;
5. reinterpret the usable history view with that snapshot when the fingerprint
   changed.

The fingerprint is not a scientific signature. Its only purposes are to notice
that derived values may be stale, invalidate caches, and explain which source
snapshot produced diagnostics. A changed fingerprint must not automatically
exclude old records. Every old record is attempted under current definitions:

- changed parameter ranges renormalize stored raw values;
- changed parameter names/count may make individual records mechanically unusable;
- changed `calc_cost.py` recalculates current costs from compatible rawData;
- changed objective names/count rebuilds the optimizer and reference directions;
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
- current objective names/costs as a derived diagnostic cache, tagged with the
  fingerprint that produced them.

Stored costs are never source truth. A reader may reuse them only as a derived cache
when the current fingerprint exactly matches; otherwise it recalculates from
rawData.

Admission accounts for the owned rawData's actual or conservative encoded-byte
size. An envelope larger than the total byte budget is dropped after current cost
is returned. Do not copy or serialize the same payload repeatedly merely to move it
between finalizer, queue, and writer.

### 4. Use one bounded background writer thread

Create one writer thread for one active campaign in one workspace. Use a daemon
thread or an equivalent lifecycle that cannot keep the interpreter alive after the
bounded shutdown deadline. Do not create one writer per backend, worker, generation,
or segment.

Initial loss/throughput profile:

- target segment: up to 16 candidates;
- total unpublished capacity: up to 32 candidates;
- segment byte cap: benchmark a bounded starting value such as 8--16 MiB;
- total unpublished byte cap: no more than twice the selected segment byte cap;
- flush a partial segment at population/generation/evaluation-call boundaries;
- no residence-time timer is required for generation-based calls.

The unpublished budget includes candidates being assembled, waiting in the queue,
encoded into a temporary file, and actively written but not atomically published.
Credits are released only after publication succeeds or the data is explicitly
dropped. This makes the actual abrupt-process-loss exposure no greater than the
documented 32-candidate/byte budget. A single failed or corrupt segment normally
loses at most 16 candidates.

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
requests a flush and joins only for a bounded deadline; remaining candidates are
counted as shutdown-dropped and process exit continues.

Expose bounded counters such as offered, admitted, published candidates/segments,
queue-dropped, oversized-dropped, write-failed, disabled-dropped, and
shutdown-dropped. Logging failure is itself non-fatal.

### 5. Publish immutable standard-ZIP segments

Use a versioned layout such as:

```text
recorded_data/
  v2/
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
  and generation fingerprint;
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
segment; its maximum candidate count is the bounded failure unit.

Run/generation/surrogate metadata must also avoid one growing mutable JSONL. Publish
small immutable event files or include the authoritative metadata in segment
manifests. Derived summaries may be rebuilt and are never required for recovery.

### 6. Keep current history hot without freezing task meaning

At campaign start, discover a stable snapshot of finalized segment names once and
build an in-memory catalog. Do not rescan the complete records tree after every
candidate or unchanged generation.

Maintain a derived in-memory history view containing raw-variable coordinates,
current costs, provenance, and references to published segment evidence. Current
generation results may enter that view immediately so the optimizer need not wait
for persistence. Retain an unpublished result's rawData only while it remains in
the bounded recorder ownership window.

Track whether each in-process row is backed by a finalized segment, still owns a
pending envelope, or has been dropped. Publication replaces pending ownership with
a segment reference. A dropped row may remain usable from its already derived
variables/costs while the generation fingerprint is unchanged, but it has no
recoverable evidence: remove it from the derived history when a later task change
requires reinterpretation, and expect it to be absent after process restart.

When the generation fingerprint is unchanged, append new derived rows and reuse
the existing view. When relevant task sources change:

1. invalidate derived normalization/cost caches;
2. take a stable snapshot of all finalized segments plus still-owned envelopes;
3. sequentially load candidate evidence and apply the new generation snapshot;
4. omit records that are missing, lost, corrupt, or mechanically uninterpretable;
5. build the next optimizer context from the new parameter/objective definitions.

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

1. Add tests for generation-boundary task/config reload, changed parameter and
   objective counts, current-cost reinterpretation, and the rule that fingerprints
   invalidate caches without making scientific compatibility decisions.
2. Refactor the existing `JobResult` finalization so all backends calculate cost
   directly from one owned validation load. Temporary old-store adapters may remain
   only during this stage.
3. Implement the standard-ZIP segment encoder/scanner and immutable run/generation
   metadata events. Verify that new writes never open older segments.
4. Implement the single bounded background thread, complete unpublished-budget
   accounting, non-blocking admission, failure disablement, and bounded shutdown.
5. Route fast, local, and distributed through the common finalizer/recorder and
   remove fast inline recording plus local/distributed batch/fallback policy.
6. Implement the hot derived-history catalog and generation-fingerprint
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
- Editing parameter ranges renormalizes stored raw variables; adding/removing or
  renaming parameters rebuilds the problem and skips only concretely unusable
  records.
- Changing objective names/count rebuilds GA/NSGA-III problem state and reference
  directions for the next generation.
- Editing workflow/evaluation/task helper code affects the next generation and
  does not split the current generation across source snapshots.
- A changed fingerprint never excludes a record by itself.
- An unchanged fingerprint does not cause a full segment-tree scan or full cost
  recalculation every generation.

### Bounded asynchronous loss

- The selected default publishes no more than 16 candidates in one segment.
- Instrumentation proves that assembling + queued + encoding + temporary +
  in-flight candidates never exceed 32 or the total byte budget.
- Queue/byte exhaustion and an oversized candidate drop immediately without
  changing the returned cost or delaying worker release.
- Segment errors lose at most that segment; later admitted segments can publish.
- Consecutive systemic failures disable recording without stopping later
  generations.
- Unexpected writer death disables recording without an automatic restart loop and
  without terminating optimization.
- Bounded shutdown reports and discards remaining candidates after its deadline.

### Format, HDD shape, and recovery

- A segment write never reads, opens, copies, appends, or modifies an earlier
  segment.
- Temporary files are ignored after abrupt termination.
- Corrupting one candidate member skips that candidate while readable siblings
  survive; corrupting the ZIP directory skips at most one 16-candidate segment.
- No per-candidate filesystem file, `fsync`, index transaction, global manifest
  rewrite, or history-directory scan exists in the hot write path.
- Instrumented tests bound file creation, directory updates, opens, flushes, and
  seek-like operations by segment count.
- A seek-penalized filesystem double favors sequential micro-batches over
  per-candidate files without requiring a physical HDD in the generic suite.
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
- Recovering queued but unpublished data after process/machine loss.
- Guaranteeing power-loss durability or flushing every candidate.
- Automatically deciding whether a user's task change is scientifically correct.
- Freezing task definitions for a campaign.
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
- one segment loses at most 16 candidates and the complete unpublished state is
  proven to remain within 32 candidates plus the byte budget;
- every injected catchable recording/read failure leaves optimization able to
  continue;
- generation-boundary edits to cost, parameters, objectives, evaluator, and config
  are supported without a scientific-equivalence gate;
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
