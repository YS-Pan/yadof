# Restore Native HTCondor Resource Retries

## Context

- Execute this manual toDo only after a newer HTCondor installation package can be
  installed successfully on the deployed submit machines and its native resource
  retry behavior has been verified in a real pool.
- The current deployment uses yadof-managed fresh submissions because the available
  HTCondor installation does not accept the required native retry submit settings.
- The temporary policy is deliberately isolated in
  `project/evaluate_manager/resource_retries.py`, with minimal orchestration in
  `condor_runner.py`.

## Goal

- Remove yadof's held-job resource retry state machine and use HTCondor's native
  bounded memory/disk retry request functionality.
- Keep generation-to-generation automatic memory/disk calibration in yadof; only
  the retry-after-resource-exhaustion mechanism moves into HTCondor.
- Preserve the current guarantees that retries are bounded and that timeout,
  workflow, and submission failures are not resource-retried.

## Guidance

- Delete `project/evaluate_manager/resource_retries.py` and its focused tests.
- Remove retry state, held-cluster removal, attempt-output cleanup, and fresh
  resubmission orchestration from `condor_runner.py`.
- Replace `YADOF_RESOURCE_RETRY_DOUBLINGS` with the native submit-file policy. Build
  finite memory and disk retry values from each concrete initial request without
  changing CPU policy or the generation-calibration behavior in
  `resource_requests.py`.
- Update retry metadata to reflect native Condor attempts using ClassAd/history data
  that the verified installation exposes; remove `yadof_resource_retry_*` fields.
- Keep `allowed_execute_duration` timeout holds terminal and non-retryable.
- Update user docs, architecture, blueprints, terminology, and the change record.
  Remove this manual toDo after completion according to the documentation rules.

## Completion Rule

- A real pool test demonstrates bounded native memory and disk retries from one
  submitted cluster without yadof removing and freshly submitting the individual.
- Generated `job.sub` files contain the verified native retry request settings, and
  no yadof retry state machine or resource-retry resubmission path remains.
- Automated tests cover finite native retry values, independent memory/disk
  behavior, terminal timeout behavior, and removal of the temporary metadata/code.
