# File blueprint: src/yadof/evaluate_manager/lifecycle.py

## Intent

- Give every backend one explicit, generation-bounded evaluation lifecycle without
  exposing worker, process, or scheduler types.

## Functionalities

- Freeze materialized candidate order, effective backend configuration, objective
  width, environment, provenance, and optional exact campaign snapshot in an
  immutable `EvaluationBatch` without opening runtime resources.
- Represent `created`, `running`, `cancelling`, `completed`, `failed`, and `closed`
  through `EvaluationHandleState`.
- Launch one non-daemon owner thread, wake every waiter on success or framework
  failure, cache exactly one immutable `EvaluationResult`, and keep wait timeouts
  non-mutating.
- Make cancellation idempotent. Before start it creates ordered in-memory cancelled
  rows but no session/evidence; after start it sets the common backend signal.
- Make close cancel/wait active work, release the campaign registry lease, and
  preserve repeated result or failure semantics. Context-manager cleanup does not
  hide an existing caller exception.

## Invariants

- A result row carries no rawData payload after finalization; durable evidence is
  read only through `recorded_data` views.
- A handle using a caller-owned campaign registers against the exact current
  snapshot at construction and remains open until close, even after completion.
- Standalone execution owns and closes its private session inside the owner thread;
  it never registers recursively with that session.
- Backend or recorder failure is re-raised by every waiter and is never converted
  to optimizer infinity.
