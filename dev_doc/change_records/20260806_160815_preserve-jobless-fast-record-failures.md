# 2026-08-06 16:08 - Preserve Jobless Fast Recording Failures

## Context

- Fast evaluation results deliberately have no durable job directory.
- When recording a completed fast result failed, the failure-isolation path passed
  that valid `None` job path to `Path()`. The resulting `TypeError` masked the
  original recording exception, aborted the remaining population, and interrupted
  fast scratch cleanup.

## Change

- Preserve `job_dir=None` when converting a jobless fast result into an error
  result.
- Add a fast evaluation regression test that injects one recording failure and
  verifies the original error metadata, infinite cost isolation, continued
  evaluation, and scratch cleanup.

## Rationale

- `JobResult.job_dir` is explicitly optional so file-backed and memory-backed
  evaluation outcomes can share the same failure and persistence contracts.
- Keeping the original exception allows the normal per-individual failure path to
  diagnose the actual recording problem instead of raising a secondary path error.

## Impact

- Fast recording failures no longer terminate the whole population merely because
  the result has no job directory.
- Local and distributed behavior is unchanged because their results retain real
  paths.
- A real fast generation with 100 candidates completed with 100 recorded successes
  and no new scratch residue after the corrected wheel was installed.

## Follow-Up

- The original recording exception did not recur in the real generation and was
  not preserved by the older masking path, so its exact transient trigger cannot be
  reconstructed from the interrupted run's durable records.
