# File blueprint: project/evaluate_manager/time_limits.py

## Intent

- Calculate the scheduler-enforced execution duration for one HTCondor job while keeping the whole-generation wait budget separate.
- Adapt normal-job limits from real execution history without ever limiting the smoke job or rewriting user config.

## Functionalities

- Return no limit for an unindexed smoke job.
- Support `fixed` mode using `HTCONDOR_JOB_TIMEOUT_SEC` directly.
- In default `auto` mode, use the newest successful distributed smoke duration for generation zero and the preceding generation from the same run thereafter.
- Subtract cumulative suspension time from remote wall-clock time when Condor ClassAds are available, with workflow `started_at`/`ended_at` as the fallback.
- Trim the configured highest fraction, treat timeout rows as infinity, and use the largest finite duration when infinity count exceeds the trim capacity.
- Apply the common timeout multiplier and fall back to the configured one-hour baseline when no finite measurement exists.
- When smoke is disabled, treat that baseline as a synthetic smoke duration before applying the multiplier.

## I/O Format

- Input: one `JobSpec` plus public `recorded_data.api.list_records()` rows.
- Output: immutable `HTCondorTimeLimit(seconds, source, sample_count)`; `seconds=None` means the submit file must omit `allowed_execute_duration`.
- Relevant metadata fields are `engine`, `condor_remote_wall_clock_sec`, `condor_cumulative_suspension_sec`, top-level workflow timestamps, status, run id, and generation index.

## Non-Obvious Techniques

- The upper-tail removal uses `ceil(sample_count * fraction)` while retaining at least one item.
- A timed-out individual is infinity for ordering, not its partial measured duration. If more infinities exist than the trim can remove, the next generation still needs a finite scheduler expression, so the controller chooses the largest finite duration; all-timeout input falls back to config.
- The same multiplier is used for smoke-to-generation-zero and preceding-generation-to-next-generation transitions.

## Mutability Profile

- Timeout statistics and config validation require focused tests because an incorrect limit can waste cluster time or terminate valid expensive evaluations.
- HTCondor enforcement mechanics belong in `condor_runner.py`; this file only calculates the value and provenance.
