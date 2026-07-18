# File blueprint: src/yadof/evaluate_manager/resource_retries.py

## Intent

- Isolate the temporary yadof implementation of memory/disk request retries so it
  can be removed cleanly when the deployed HTCondor supports the native feature.

## Functionalities

- Classify only standard HTCondor out-of-resources holds: reason code `34` with
  subcode `102` for memory or `104` for disk.
- Hold immutable per-individual state containing the current concrete request,
  independent memory/disk retry counts, configured per-resource limit, and attempt
  history.
- Double only the exhausted resource and leave CPU and the other resource unchanged.
- Return a terminal exhausted decision after `YADOF_RESOURCE_RETRY_DOUBLINGS`
  successful doublings for that resource.
- Produce JSON-compatible retry metadata and remove stale per-attempt outputs before
  the runner submits a fresh cluster. Preserve static job inputs and submit-side
  `metadata.json`/`metaData.json`.

## I/O Format

- Input: `HTCondorResourceRequest`, hold-info mappings, optional ClassAd usage
  mappings, cluster id, and a prepared job directory.
- Output: `YadofResourceRetryDecision` with the new state and a `should_retry` flag;
  metadata keys use the `yadof_resource_retry_*` prefix.
- The module performs no Condor command execution. `condor_runner.py` owns querying,
  removing the old cluster, and submitting the returned request.

## Non-Obvious Techniques

- Numeric reason/subreason codes are the contract; reason text is diagnostic only.
- Retry counts are independent so a memory retry does not consume the disk budget.
- A fresh attempt must not see old `condor.log`, cluster id, stdout/stderr,
  `individual_metadata.json`, `rawData/`, transfer archives, or sandbox profile/temp
  directories. Source inputs and submit-side metadata remain in place.
- Timeout holds, workflow errors, submit failures, cleanup failures, and unknown
  holds return no resource retry. The runner's existing generation deadline covers
  every attempt.

## Mutability Profile

- Keep this file self-contained and avoid spreading retry policy into config,
  request calibration, or result-recording modules.
- Delete this module and its focused tests when the manual native-HTCondor retry
  migration toDo is executed; retain only minimal runner changes needed for the
  replacement behavior.
