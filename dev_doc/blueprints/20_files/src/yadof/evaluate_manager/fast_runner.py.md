# File blueprint: src/yadof/evaluate_manager/fast_runner.py

## Intent

Execute immutable candidate batches through bounded reusable task sessions.

## Functionalities

- `FastWorkerPool` owns non-daemon spawn workers, session scratch and process handles.
  Its compatibility key includes evaluation signature, environment, cap and timeout.
- Serialize use of a pool; open each task session lazily in its worker and retain
  it across compatible batches. Detect idle worker death before assigning work.
- Give each candidate separate scratch and context, bound diagnostic tails, and
  return complete named rawData and typed physical-failure metadata in input order.
- Preserve usable sessions after success or declared physical failure. Replace
  other task errors; kill trees after timeout, crash or cancellation. Close asks
  for graceful session cleanup then applies bounded process-tree cleanup.
- Report whether a kernel was invoked; pass completions to the caller's consumer.
  Formal evaluation uses the common finalizer; oracle consumers do not record.

## Invariants

- No cost calculation, model training, evidence publication or result cache.
- A campaign owns supplied pools; a standalone call closes its own pool.
- No descendant kill after a normal result: resident simulators belong to sessions.
- Closing a pool removes only its owned scratch and releases Windows process handles.
- Lifecycle tests cover A/B/A, physical failure recovery, replacement, invalidation,
  active cancellation, snapshot cleanup and independent workspace isolation.
