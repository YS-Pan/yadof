# Module blueprint: evaluate_manager

## Responsibility

`yadof.evaluate_manager` turns normalized candidates into fast logical evaluations
or prepared jobs, executes them in reusable local workers, prepared local
subprocesses, or HTCondor, and normalizes every outcome into ordered `JobResult`
rows. One population-scoped coordinator publishes bounded owned-evidence groups
before deriving current cost in stable population order. A preparation, execution,
collection, rawData, or cost failure affects only its candidate; valid rawData
remains durable completed evidence even when its current interpretation fails. Recorder
backpressure may delay worker reuse or population completion; recorder failure
stops the campaign before later evaluation.

`resource_calibration.py` is the shared automation boundary. It reads backend-neutral
resource keys with legacy backend-key fallback, selects compatible smoke or
preceding-generation records, trims high samples, applies generation-zero bootstrap
scaling, and returns one immutable per-job estimate.

## Job preparation

`job_files.py` creates a collision-safe directory, copies only evaluate-side
`job_template/` inputs while excluding runtime artifacts (including current/legacy
worker profile/temp directories) and canonical unassigned parameters, rejects
misplaced `calc_cost.py`/`optimization.py`, and excludes direct
`job_template/` children whose names end case-insensitively with `.aedtresults` or
`.aedt.lock`. The suffix filter is intentionally top-level only. Preparation then
materializes a self-contained assigned parameter snapshot, copies only package
`worker_misc.py` containing the invariant execute lifecycle, creates empty
`rawData/`, computes a definition-oriented static hash, and writes preparation
metadata. It never reads/copies the complete `submit/` tree or transfers a yadof
runtime package/archive/config.

## Local backend

`local_runner.py` directly runs job-local `workflow.py` with bounded concurrency and
per-job timeout, kills the process tree on timeout, rejects `cost.json`, validates
the flat rawData directory even when no direct files exist, merges workflow metadata,
and captures output tails. psutil samples the workflow and recursive simulator
children to record summed peak RSS, accumulated CPU time/average cores, peak process
count, and job-directory disk use. `local_resources.py` combines calibrated per-job
needs with physical CPU, currently available memory, free disk, reserve fraction,
population size, and the configured worker cap. The task workflow calls package
worker support, which records the execute-machine name and the rest of the invariant
lifecycle metadata.

## Fast backend

`fast_runner.py` maintains a bounded pool of non-daemon spawn workers so a kernel
may launch external simulator descendants. Each worker handles one candidate at a
time and returns a mapping of unique direct `.npz` basenames to validated in-memory
payloads plus JSON diagnostics. A bounded pipe holds at most one result per worker;
the parent admits each completion to the population coordinator before assigning
more work, and count/byte target commits may expose several ordered results
together. Every worker uses the generation's immutable task snapshot. There is no
`prepare_job()`, job-template copy, assigned parameter file, workflow process, or
fake job path. `fast_resources.py` bounds the configured cap by population and
declared per-worker CPU/memory/scratch disk against current host capacity.

The parent owns candidate scratch creation/cleanup, records worker/machine/timing
and process-tree diagnostics, enforces the hard timeout, and uses shared
`process_control.py` to reap remaining descendants after every response or kill a
timed-out/crashed worker tree. A failure discards that worker and creates a
replacement. A successful worker is reused after descendant cleanup. Fast worker
plans are stored in evaluation metadata, not emitted once per generation as CLI
progress. Fast never calls the scheduler-specific `after_jobs_submitted` callback.

## Distributed backend

`condor_runner.py` writes Windows direct-workflow submit files, selects only needed
job inputs, explicitly returns `rawData.zip` plus individual metadata instead of the
`rawData/` directory, restores only unique direct `.npz` archive members, validates
them, queries queue/history ClassAds, derives active execution wall-clock from
submit-side event logs, retains the active/last timeout execution site's machine
and slot as source-labeled fallback provenance, and removes terminal
held/timed-out jobs when needed. A per-job timeout becomes locally final even when
bounded `condor_rm` cleanup fails. Normal policy is `run_as_owner=False`,
`load_profile=True`; pool repair is outside the module.

Distributed completion callbacks enter the same coordinator used by fast and local;
`RecordingError` is never swallowed as a progress-callback failure, and no backend
contains a persistence branch or publication fallback.

When CLI progress is active, the manager owns one backend-neutral population bar.
Fast reports after current-cost finalization; local reports each completed future;
distributed receives terminal results through the Condor runner's result callback.
Preparation failures count immediately. Each population index is idempotent, and
the population does not return until its recorder flush has completed.

Distributed support preserves concrete CPU/memory/disk requests, workspace-local
calibration, bounded yadof memory/disk resubmission, automatic/fixed scheduler
execution limits enforced both by Condor and a submit-side yadof watchdog, unlimited
smoke, whole-generation deadlines, final ClassAd data, output restoration, and
Windows slot-user policy. Pending jobs may receive one delayed read-only matchmaking
analysis. The module diagnoses but never repairs HTCondor.

`worker_misc.run_workflow()`, invoked by `workflow.py`, samples the primary
execute-machine identity on the execute node, writes `execute_machine` into
`individual_metadata.json`, and returns that file through normal transport. When a
timeout prevents the transfer, `condor_runner` may record lower-priority
`condor_execute_machine`/slot provenance from that job's own user log. ClassAds do
not override either source, and a never-executed job remains unassigned.

HTCondor ClassAd resource measurements and local process-tree measurements both
publish `resource_cpu_usage_cores`, `resource_memory_usage_mib`, and
`resource_disk_usage_kib`. Condor request formatting and local worker planning call
the same calibration module; only backend-specific enforcement remains separate.

## Recording and cost return

`finalizer.py` converts file-backed or memory-backed evidence to owned validated
envelopes, groups admission by the frozen recorder targets, waits for committed
receipts, and only then calculates cost with one frozen generation interpreter in
population order. Execution failures publish diagnostic rows and skip cost. A cost
interpretation failure preserves immutable completed evidence and returns no
authoritative cost; the evaluator adapter supplies `inf` with current objective
width. Result order always matches candidate order, and every dispatch resolves the
population's receipts before return.

## Invariants

- Fast/local/distributed share validation, group publication, receipt, cost,
  ordering, and shape rules;
  only local/distributed share prepared-job composition.
- Standalone smoke is exactly one midpoint job and has no job/generation timeout.
- Local default worker cap is eight; adaptive planning may safely choose fewer and
  never exceeds the population or cap.
- Resource retries are bounded fresh clusters for standard memory/disk holds only.
- Submit callbacks run after submission and cannot cancel queued jobs on failure.
- Every stateful lookup uses the effective workspace.
