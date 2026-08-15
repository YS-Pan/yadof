# File blueprint: src/yadof/recorded_data/session.py

## Intent

- Own the complete in-memory and asynchronous persistence lifetime of one campaign.

## Functionalities

- Acquire the campaign OS lock, discover finalized segments once, and maintain a
  private catalog of durable plus accepted current rows.
- Create one immutable generation task snapshot per boundary, validate stable
  parameter/objective shapes, and reinterpret history only when its interpretation
  fingerprint changes.
- Admit owned envelopes without blocking against exact candidate and conservative
  byte budgets; one daemon writer batches by run/generation and selected limits.
- Flush generation boundaries, continue after isolated write failures, open a
  circuit breaker after repeated failures, contain writer death, and perform bounded
  shutdown with explicit queued/in-flight accounting.

## Invariants

- Exactly one writer exists per campaign and no per-candidate thread is created.
- Recorder path/capacities remain frozen from campaign start.
- A dropped row remains usable only under its already-derived interpretation; it
  disappears when later task reinterpretation would require missing evidence.
- Every refusal/loss/death/shutdown condition is reflected in monotonic counters and
  bounded warnings, never in current evaluation cost.
