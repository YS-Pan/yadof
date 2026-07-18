# File blueprint: src/yadof/evaluate_manager/condor_runner.py

## Intent
- Submit prepared jobs to HTCondor, then collect job-local outputs using the shared evaluation result contract.

## Functionalities
- Submit one `job.sub` per prepared `JobSpec`.
- Write Windows HTCondor submit files from values exposed by `the workspace LoadedConfig` through `evaluate_manager.config` and the adaptive `resource_requests`/`time_limits` helpers.
- Invoke an optional `after_jobs_submitted` callback after successful submissions and before polling outputs.
- Poll terminal job state or complete returned outputs, collect rawData and metadata, query final `condor_history`/held-job ClassAds for resource and execution-time measurements, and turn failures/timeouts into `JobResult` rows.
- Recognize `allowed_execute_duration` hold codes 46/47 as timeouts, capture their diagnostics, and remove the held job so it cannot be retried.
- Delegate standard memory/disk resource-hold decisions and attempt cleanup to
  `resource_retries.py`, remove the old cluster, and submit a fresh cluster with the
  returned concrete request while preserving retry metadata.
- Isolate per-job collection failures so one bad returned payload cannot fail the whole generation.

## I/O Format
- Input is prepared job specs.
- Output is ordered `JobResult` rows.
- Callback has no arguments and its return value is ignored.
- Submit files use `executable = workflow.py`, omit the workflow argument line, set `transfer_executable = True`, and use the calculated `request_cpus`, `request_memory`, and `request_disk` values. They do not emit Condor-native resource retry directives. Normal generation jobs emit the calculated `allowed_execute_duration`; smoke jobs omit it.
- `environment` is emitted as one quoted HTCondor environment string. Entries must be whitespace-separated inside that quoted string; semicolon-separated entries are not valid for the current submit style.

## Non-Obvious Techniques
- The after-submit callback is designed for submit-side surrogate training. Callback failure is logged but must not cancel already-submitted HTCondor jobs.
- `condor_environment_string()` only escapes quotes and rejects newlines. It does not translate semicolon-delimited legacy syntax; config must provide the intended HTCondor syntax directly.
- The generic environment comes from `the workspace LoadedConfig`; active software-specific entries are contributed through `workspace task/environment settings`. The HFSS extension may deliberately pass more solver cores than `HTCONDOR_REQUEST_CPUS` through `HFSS_CPUCORE_MULTIPLIER`; those are not extra scheduler-reserved cores.
- `condor_resource_usage()` reads a final JSON ClassAd from `condor_history`, then
  falls back to `condor_q` for a still-held job. It records peak `MemoryUsage`,
  execute-directory `DiskUsage`, `RemoteWallClockTime`,
  `CumulativeSuspensionTime`, and related request/CPU values as diagnostics but
  never turns an unavailable history query into a result-collection failure.
- Nested `rawData/*.npz` files take precedence over `rawData_outputs.zip`. The zip is only a fallback for older transfer behavior, and restore failures are recorded in metadata instead of escaping from collection.
- A resource retry is a new cluster, not a Condor restart inside the old cluster. The
  old held cluster must be removed before attempt outputs are reset, and every retry
  remains inside the original generation-level deadline. Timeout, workflow, submit,
  cleanup, and non-resource hold failures are never resource-retried.

## Mutability Profile
- HTCondor submit details may change, but the callback location must remain after submission and before waiting if staggered training is to keep the cluster busy.
- Keep resource policy in `resource_retries.py`; the runner should contain only the
  minimal orchestration needed to query, remove, reset, and resubmit so native
  Condor retry support can replace it cleanly later.
