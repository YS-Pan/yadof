# File blueprint: src/yadof/recorded_data/session.py

## Intent

- Own the complete in-memory and backpressured persistence lifetime of one campaign.

## Functionalities

- Acquire the campaign OS lock, discover finalized segments once, and maintain a
  private catalog with explicit pending/committed/failed current-row states.
- Create one immutable generation task snapshot per boundary, validate stable
  parameter/objective shapes, and reinterpret history only when its interpretation
  fingerprint changes.
- Freeze immutable live `EvidenceDataset` views containing accepted pending,
  committed, and recording-failed rows. Pending rows have no readable rawData;
  committed rows use durable references rather than retained envelopes.
- Build a snapshot-bound `CostTable`, reuse same-fingerprint transient hints, and
  update only the session interpretation cache without rewriting evidence.
- Expose transient named rawData samples, including exact direct `.npz` basenames,
  for schema adapters that must freeze selector identity. This read view neither
  changes persistence nor retains a second evidence store.
- Expose copied task/runtime record metadata aligned by stable job name so a
  task-owned hierarchical-CAE frequency filter can assess the same durable/current rows without
  embedding executable callbacks or changing rawData.
- Admit owned envelopes against exact candidate and conservative byte budgets and
  return candidate/group publication receipts. Producers wait when capacity is full
  while one writer batches by run/generation and selected limits.
- Resolve receipts only after immutable publication, retain committed payloads only
  within explicit count/byte limits, spill excess ownership to durable references,
  and attach transient interpretation state without rewriting segment records.
- Wait for durable generation boundaries, retry the same retained batch after
  transient write failures, propagate exhausted retries or writer death as
  `RecordingError`, and wait for queued/in-flight work during shutdown.
- Register evaluation/training handles that reuse the exact current snapshot,
  retain their normal-boundary `wait`/`cancel` policy, reject a later generation
  while any registered handle remains open, expose `finish_generation()`, and
  cancel/close all handles before writer shutdown and snapshot deletion.

## Invariants

- Exactly one writer exists per campaign and no per-candidate thread is created.
- Recorder path/capacities remain frozen from campaign start.
- Every finalized row is durably published before later evaluation or the campaign
  stops visibly; no queue-full, failure, or shutdown path silently drops it.
- Queue admission is pending, never committed. Writer failure resolves every
  retained or blocked receipt failed within the writer's bounded failure path.
- Backpressure and retry activity is reflected in monotonic counters.
- Dataset/cost views preserve candidate and row identity; only successful committed
  original rows can become optimizer history.
- Handle close never waits while holding the session state lock; result callbacks
  may therefore finish recording during session-driven cancellation without a
  close deadlock.
- Normal generation completion waits for training publication; abnormal session
  close requests cooperative cancellation before recorder/snapshot teardown.
