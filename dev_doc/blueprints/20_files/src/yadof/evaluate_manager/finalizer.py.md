# File blueprint: src/yadof/evaluate_manager/finalizer.py

## Intent

- Give fast, local, and distributed evaluations one bounded population-finalization
  path whose evidence must commit before current-cost interpretation begins.

## Functionalities

- Normalize every backend outcome into an ordered `JobResult` with campaign and
  generation-snapshot provenance. Finalized payload-free metadata includes the
  durable candidate/evidence identity and committed receipt/group state.
- Validate and own file-backed or memory-backed rawData exactly once, admit it into
  a count/byte-targeted group, and retain only payload-free result state outside the
  recorder's ownership budget.
- Wait for pending/committed/failed publication receipts, then use one frozen cost
  interpreter in deterministic population order.
- Keep execution, evidence, and interpretation states independent. RawData failure
  produces no completed evidence; cost failure leaves completed evidence committed
  and returns a replayable interpretation diagnostic. Cancelled execution publishes
  no rawData and receives a not-applicable interpretation.
- Record validation, admission, completion-to-commit, and commit-to-interpretation
  timings.

## Invariants

- The coordinator flushes on existing segment count/byte targets or an explicit
  population tail; it does not serialize normal production into singleton writes.
- Cost never starts before its receipt is committed. A process lost afterward may
  leave interpretation missing while a new session still recovers evidence.
- Envelope-construction/admission/publication failure is a recording error and
  wakes all related waiters.
- Backends do not contain independent persistence branches.
