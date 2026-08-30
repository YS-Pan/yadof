# File blueprint: src/yadof/recorded_data/session.py

## Intent

- Own the complete in-memory and backpressured persistence lifetime of one campaign.

## Functionalities

- Acquire the campaign OS lock, discover finalized segments once, and maintain a
  private catalog with explicit pending/committed/failed current-row states.
- Create one immutable generation task snapshot per boundary, validate stable
  parameter/objective shapes, and reinterpret history only when its interpretation
  fingerprint changes.
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

## Invariants

- Exactly one writer exists per campaign and no per-candidate thread is created.
- Recorder path/capacities remain frozen from campaign start.
- Every finalized row is durably published before later evaluation or the campaign
  stops visibly; no queue-full, failure, or shutdown path silently drops it.
- Queue admission is pending, never committed. Writer failure resolves every
  retained or blocked receipt failed within the writer's bounded failure path.
- Backpressure and retry activity is reflected in monotonic counters.
