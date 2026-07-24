# 2026-07-24 09:22 - Submit-Side Distributed Per-Job Timeout

## Context

- A real distributed generation left four jobs executing for several hours after
  their calculated per-job limit while the controller continued waiting.
- The current package wrote `allowed_execute_duration` and recognized Condor timeout
  holds, but it had no independent yadof per-job watchdog. Its only submit-side
  deadline covered the whole generation.
- Condor event logs already record when each cluster enters and leaves execution, so
  the submit host can measure execution wall-clock without counting matchmaking or
  transfer delay.

## Change

- Added a local `condor.log` execution clock that starts on event `001`, pauses for
  suspension, ends on eviction/termination/hold/removal, and resets on a later
  execution event.
- Stored each calculated `HTCondorTimeLimit` with its live submission and checked
  that clock during normal polling.
- When the limit is reached, yadof now finalizes a timeout result, removes the job
  from its pending set, and attempts `condor_rm` with a five-second command timeout.
  Cleanup failure is diagnostic metadata and cannot keep local orchestration waiting.
- Kept Condor `allowed_execute_duration` and the separate whole-generation deadline
  as additional enforcement layers.
- Added focused parser, timeout-finalization, and bounded-cleanup tests and updated
  architecture, blueprints, terminology, and agent guidance.

## Rationale

- Scheduler enforcement remains desirable, but controller correctness must not
  depend on a hold event being emitted and returned correctly.
- Submission time is not an execution clock: jobs may wait for matchmaking, input
  transfer, or an available license. Local event timestamps provide the necessary
  boundary while remaining available when queue/history queries are unreliable.
- `condor_rm` is cleanup, not acknowledgement. A bounded attempt prevents a missing,
  failed, or hung command from defeating timeout semantics.

## Impact

- Distributed normal jobs now have scheduler and yadof per-job enforcement using
  the same adaptive limit.
- Timeout metadata records the enforcement source, limit, execution start and
  elapsed wall-clock, suspension state, and any removal error.
- Standalone smoke remains unlimited, and memory/disk retries still start a fresh
  cluster and execution clock under the original generation deadline.
