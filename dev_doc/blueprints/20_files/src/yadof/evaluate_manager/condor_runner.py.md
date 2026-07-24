# File blueprint: src/yadof/evaluate_manager/condor_runner.py

## Intent
- Submit prepared jobs to HTCondor, then collect job-local outputs using the shared evaluation result contract.

## Functionalities
- Submit one `job.sub` per prepared `JobSpec`.
- Write Windows HTCondor submit files from the workspace `LoadedConfig` through `evaluate_manager.config` and the adaptive `resource_requests`/`time_limits` helpers.
- Invoke an optional `after_jobs_submitted` callback after successful submissions and before polling outputs.
- Poll terminal job state or complete returned outputs, collect rawData and metadata, query final `condor_history`/held-job ClassAds for resource and execution-time measurements, and turn failures/timeouts into `JobResult` rows.
- Parse local `condor.log` event timestamps to measure the current active execution
  segment, excluding queued, evicted-idle, and suspended intervals. Enforce each
  normal job's calculated time limit independently of scheduler enforcement.
- On a yadof-detected per-job timeout, invoke `condor_rm` with a bounded command
  wait, preserve cleanup failure metadata, finalize timeout locally, and remove the
  job from the local pending set without waiting for queue confirmation.
- Recognize `allowed_execute_duration` hold codes 46/47 as timeouts, capture their diagnostics, and remove the held job so it cannot be retried.
- Delegate standard memory/disk resource-hold decisions and attempt cleanup to
  `resource_retries.py`, remove the old cluster, and submit a fresh cluster with the
  returned concrete request while preserving retry metadata.
- Isolate per-job collection failures so one bad returned payload cannot fail the whole generation.
- After a representative job remains pending for a bounded delay, run one read-only
  HTCondor matchmaking analysis and print failed requirement details. Do not remove
  or fail jobs merely because no slot currently matches.

## I/O Format
- Input is prepared job specs.
- Output is ordered `JobResult` rows.
- Callback has no arguments and its return value is ignored.
- Submit files use `executable = workflow.py`, omit the argument line, and set
  `transfer_executable = True`. The executable is not duplicated in
  `transfer_input_files`; selected task/support inputs are transferred from the job
  folder. No yadof package, wheel, runtime archive, or worker config is transferred.
  The submit file explicitly declares
  `transfer_output_files = rawData.zip,individual_metadata.json`, so Condor does not
  return `rawData/`. Calculated `request_cpus`, `request_memory`, and `request_disk`
  values are emitted. Normal jobs emit `allowed_execute_duration`; smoke jobs omit
  it. Condor-native resource retry directives are not emitted.
- `environment` is emitted as one quoted HTCondor environment string. Entries must be whitespace-separated inside that quoted string; semicolon-separated entries are not valid for the current submit style.

## Non-Obvious Techniques
- The after-submit callback is designed for submit-side surrogate training. Callback failure is logged but must not cancel already-submitted HTCondor jobs.
- `condor_environment_string()` only escapes quotes and rejects newlines. It does not translate semicolon-delimited legacy syntax; config must provide the intended HTCondor syntax directly.
- Transfer-list filenames containing spaces are emitted literally. Windows Condor
  treats surrounding double quotes as filename characters; commas/newlines are
  rejected because they cannot be represented safely in the comma-delimited list.
- The direct executable is the mutable task `workflow.py`, matching the validated
  Windows HTCondor deployment contract. The prepared assigned parameter snapshot is
  self-contained and the only package-provided runtime helper is same-directory
  `worker_misc.py`; worker startup neither receives nor imports yadof. Task and
  third-party dependencies must be job-local or intentionally installed on execute
  nodes.
- The generic environment comes from `the workspace LoadedConfig`; active software-specific entries are contributed through `workspace task/environment settings`. The HFSS extension may deliberately pass more solver cores than `HTCONDOR_REQUEST_CPUS` through `HFSS_CPUCORE_MULTIPLIER`; those are not extra scheduler-reserved cores.
- `condor_resource_usage()` reads a final JSON ClassAd from `condor_history`, then
  falls back to `condor_q` for a still-held job. It records peak `MemoryUsage`,
  execute-directory `DiskUsage`, `RemoteWallClockTime`,
  `CumulativeSuspensionTime`, and related request/CPU values as diagnostics but
  never turns an unavailable history query into a result-collection failure.
- The yadof watchdog follows event `001` (`Job executing`) and the corresponding
  eviction/termination/hold/removal events instead of submission time, so
  matchmaking and input-transfer delay cannot consume a job's execute budget.
  Suspension/unsuspension events pause/resume the clock. A later execute event starts
  a fresh active segment.
- `rawData.zip` is the only distributed rawData transport. It is required, readable,
  and may contain only unique direct `.npz` members; directories, nested paths,
  other extensions, and case-insensitive duplicates are errors. Collection restores
  those files directly into submit-side `rawData/`, validates the directory, and
  records restoration errors per job rather than escaping across a generation.
- A resource retry is a new cluster, not a Condor restart inside the old cluster. The
  old held cluster must be removed before attempt outputs are reset, and every retry
  remains inside the original generation-level deadline. Timeout, workflow, submit,
  cleanup, and non-resource hold failures are never resource-retried.
- Non-resource held jobs are removed after their hold ClassAd is captured so a
  completed controller call does not leave a persistent held cluster behind.
- `condor_rm` is cleanup rather than acknowledgement: timeout state is authoritative
  on the submit side, and command failure or timeout cannot return a job to the
  pending set.
- Matchmaking diagnostics use `condor_q -better-analyze:nouserprios` for one pending
  cluster only. They are delayed to avoid adding work to short jobs and summarized
  to the failed requirement, no-match warning, and last match failure.

## Mutability Profile
- HTCondor submit details may change, but the callback location must remain after submission and before waiting if staggered training is to keep the cluster busy.
- Keep resource policy in `resource_retries.py`; the runner should contain only the
  minimal orchestration needed to query, remove, reset, and resubmit so native
  Condor retry support can replace it cleanly later.
- Keep direct workflow execution and explicit zip-only rawData transfer aligned with
  `admin_tool/htcondor_doc/deployment_contract.md`. Do not insert an intermediary
  launcher unless that administrator contract is intentionally revised.
