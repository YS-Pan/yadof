# 2026-08-24 10:30 - Require Reliable Evaluation Recording

## Context

- The earlier segmented recorder deliberately favored simulator throughput: final
  costs entered the optimizer before a non-blocking bounded offer, so a full queue,
  slow disk, write failure, or bounded shutdown could discard evidence while later
  simulation continued.
- A 20-generation, 100-individual benchmark exposed many missing `test_com`
  results. Increasing the benchmark's unpublished-candidate limit reduced pressure
  but did not change the framework's loss-tolerant contract.
- The user explicitly reversed that product priority. Complete result history now
  matters more than recorder throughput: slow publication must delay later
  simulation, and yadof must not continue after an unpersisted result.

## Change

- Replaced full-budget admission refusal with condition-based backpressure. The
  writer retains bounded candidate/byte ownership, wakes producers when publication
  releases credits, and exposes wait counts/timing instead of drop counters.
- Made every evaluation/population flush boundary wait until all queued and
  in-flight envelopes are atomically published. Micro-batch ZIP segments and the
  single workspace writer remain intact.
- Changed transient segment failure to retry the same retained batch. Exhausting
  `HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES`, exceeding the explicit single-record
  safety limit, envelope-construction failure, duplicate campaign candidate
  identity, or unexpected writer death raises `RecordingError` and stops the
  campaign before later evaluation.
- Removed the lossy writer-shutdown timeout. The writer is non-daemon and campaign
  close waits for queued and in-flight publication while retaining the workspace
  lock.
- Removed the now-unread `_publishing` flag left behind by the old bounded-shutdown
  branch; active-batch ownership is the single remaining in-flight state.
- Updated active architecture, blueprints, terminology, user guidance, the parked
  refinement handoff, and the persistent recording-consistency guard to describe
  reliable backpressure and boundary durability. Historical change records and
  obsolete plans remain unchanged as evidence of the superseded decision.

## Rationale

- Backpressure addresses the actual speed mismatch without creating an unbounded
  queue. Waiting at the population boundary preserves segment micro-batching while
  guaranteeing that a later generation cannot outrun durable history.
- A persistent storage failure cannot satisfy the durability guarantee. Stopping
  with a specific error is safer than silently losing evidence or treating the
  infrastructure problem as an ordinary scientific `inf` result.

## Impact

- Fast mode may pause worker reuse when the unpublished budget is full. Local and
  distributed work already submitted may finish concurrently, but no dispatch
  returns and no later generation starts until the recorder is empty.
- `HISTORY_UNPUBLISHED_MAX_CANDIDATES` and
  `HISTORY_UNPUBLISHED_MAX_BYTES` now control bounded backlog/backpressure rather
  than acceptable loss. `HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES` is the number of
  attempts for the same retained batch.
- `HISTORY_WRITER_SHUTDOWN_TIMEOUT_SEC` is no longer a supported config setting.
  No repository example or benchmark baseline set it.

## Follow-Up

- Re-run the long benchmark only when separately authorized; the package tests use
  blocked-writer and injected-failure fixtures to verify the new concurrency and
  failure semantics without starting a simulator.
