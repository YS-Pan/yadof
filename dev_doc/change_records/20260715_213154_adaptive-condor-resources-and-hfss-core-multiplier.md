# 2026-07-15 21:31 - Adaptive Condor Resources And HFSS Core Multiplier

## Context

- HFSS uses its configured solver cores unevenly over an evaluation, so a scheduler
  CPU reservation equal to the solver target can leave execute-node CPU capacity
  underused for much of the job.
- Memory and execute-scratch requirements vary by individual. A fixed request
  either over-reserves every job or occasionally causes an avoidable resource hold.

## Change

- Added `HFSS_CPUCORE_MULTIPLIER` to the HFSS-specific config, defaulting to `2`.
  It derives the runtime HFSS core count from the manual Condor CPU request without
  changing that scheduler request.
- Added generation-aware memory/disk request calculation. A distributed smoke test
  seeds generation zero with a bootstrap multiplier; later generations use the
  previous same-run generation after trimming its high tail.
- Submit files now use calculated requests, finite doubling retry ladders for
  memory and disk, and final `condor_history`/held-job ClassAd observations returned
  in result metadata.
- Added the user disk multiplier, focused tests, architecture/blueprint/user-doc
  updates, and an exact automatic-toDo timestamp expiry contract.

## Rationale

- `MemoryUsage` is a peak ClassAd measurement and `request_memory`/`request_disk`
  are scheduler capacities, so prior per-job measurements are appropriate evidence
  for the next request. The trimming rule prevents one exceptional job from
  setting every normal job's reservation while retries protect the tail.
- CPU overuse beyond a Condor reservation is not an extra allocation. The multiplier
  is deliberately a user-selected throughput trade-off, with its limitation made
  explicit in the user documentation.

## Impact

- Distributed job metadata now contains requested resource values, calibration
  source/sample count, and final Condor resource readings when available.
- `indMeta.jsonl` retains those nested metadata fields for the next generation's
  calculation; source config files are not rewritten at runtime.
- Automatic toDo time limits now use the filename's exact local date/time and
  archive only strictly after the calculated deadline.

## Follow-Up

- A real pool smoke test should verify that its installed HTCondor version returns
  JSON ClassAds through `condor_history` and that resource evictions advance through
  the emitted retry ladder as expected.
