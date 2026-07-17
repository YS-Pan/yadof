# 2026-07-17 19:33 - Move Resource Retries Into Yadof

## Context

- The available older HTCondor installation reports native resource-retry submit
  settings as unused, while a newer installer cannot currently be installed.
- Keeping one part of memory/disk request adaptation in yadof and retry changes in
  HTCondor made the deployed behavior incomplete and difficult to diagnose.

## Change

- Removed native `retry_request_memory` and `retry_request_disk` emission from
  generated submit files and removed retry ladders from `resource_requests.py`.
- Added `evaluate_manager/resource_retries.py` as an isolated yadof-side state
  machine for standard memory/disk resource holds.
- `condor_runner.py` now removes a resource-held cluster, clears attempt artifacts,
  and freshly submits the same prepared individual with only the exhausted request
  doubled. Memory and disk retry counts are independent and bounded by
  `YADOF_RESOURCE_RETRY_DOUBLINGS`, default `4`.
- Added generic tests for hold classification, doubling/exhaustion, cleanup,
  resubmission, and absence of Condor-native retry directives.

## Rationale

- Yadof now owns every resource-request change: recorded measurements determine the
  next generation's initial request, and the isolated retry state machine determines
  per-individual request increases. HTCondor only enforces the concrete request for
  each submitted attempt.
- Isolating the temporary policy minimizes the work needed to remove it when native
  HTCondor retry support becomes deployable again.

## Impact

- Standard HTCondor out-of-memory/out-of-disk holds can recover under the installed
  scheduler without unsupported submit settings.
- Each retry is a fresh cluster and restarts workflow work from the beginning. All
  attempts share the original generation wait budget.
- Timeout, workflow, submit, cleanup, and non-resource hold failures remain terminal
  and are not retried.

## Follow-Up

- Execute `dev_doc/toDo/20260717_193325_restore-native-htcondor-resource-retries.md`
  after a newer HTCondor installation and native retry behavior are verified.
