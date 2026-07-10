# 2026-07-10 10:37 - HTCondor Result Collection Isolation

## Context
- A distributed optimization run produced completed HTCondor jobs whose workflows returned `done`, but generations 1 and 2 were recorded as all `error`.
- The recorded failure was `BadZipFile: File is not a zip file` at the run stage, which means one returned payload escaped from `run_condor_jobs()` and was converted into a generation-wide backend failure.

## Change
- `condor_runner` now waits for terminal state or complete returned outputs before collecting jobs.
- Returned nested `rawData/*.npz` files are used before attempting the legacy `rawData_outputs.zip` fallback.
- Bad fallback zip files are recorded as per-job diagnostics instead of being raised.
- Unexpected per-job collection exceptions are converted to per-job `JobResult` error rows so other jobs in the generation can still finalize.
- Added HTCondor runner tests for bad fallback zip handling and collection-failure isolation.

## Rationale
- HTCondor output transfer can expose job-local files while related payloads are still settling.
- A compatibility fallback archive should not override valid returned rawData, and one malformed or partial returned file must not invalidate the whole generation.

## Impact
- Distributed runs should no longer turn an entire generation into `error` because one `rawData_outputs.zip` could not be opened.
- Existing recorded error rows remain historical run data; users may rerun or clean history separately if those rows should not participate in later inspection.

## Follow-Up
- No new user-facing setting is required.
