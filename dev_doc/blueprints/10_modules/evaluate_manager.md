# Module blueprint: evaluate_manager

## Responsibility

`yadof.evaluate_manager` turns normalized candidates into prepared jobs, executes
them locally or through HTCondor, normalizes every outcome into ordered `JobResult`
rows, records durable evidence, and derives current costs. A preparation, execution,
collection, recording, or cost failure affects only its candidate.

## Job preparation

`job_files.py` creates a collision-safe directory, copies task inputs while
excluding runtime/submit artifacts and `calc_cost.py`, materializes a self-contained
assigned parameter snapshot, copies only package `worker_misc.py`, creates empty
`rawData/`, computes definition-oriented static hash, and writes preparation
metadata. It never creates or transfers a yadof runtime package/archive/config.

## Local backend

`local_runner.py` directly runs job-local `workflow.py` with bounded concurrency and
per-job timeout, kills the process tree on timeout, rejects `cost.json`, validates
the flat rawData directory even when no direct files exist, merges workflow metadata,
and captures output tails.

## Distributed backend

`condor_runner.py` writes Windows direct-workflow submit files, selects only needed
job inputs, explicitly returns `rawData.zip` plus individual metadata instead of the
`rawData/` directory, restores only unique direct `.npz` archive members, validates
them, queries queue/history ClassAds, and removes terminal held jobs when needed.
Normal policy is `run_as_owner=False`, `load_profile=True`; pool repair is outside
the module.

Completed population results use the recorded-data batch fast path so large archives
are copied once per population rather than once per individual. A batch failure is
retried through the single-result path to preserve failure isolation.

Distributed support preserves concrete CPU/memory/disk requests, workspace-local
calibration, bounded yadof memory/disk resubmission, automatic/fixed scheduler
execution limits, unlimited smoke, whole-generation deadlines, final ClassAd data,
output restoration, and Windows slot-user policy. Pending jobs may receive one
delayed read-only matchmaking analysis. The module diagnoses but never repairs
HTCondor.

## Recording and cost return

Completed population results use the batch recording path and one cost query. If
batch publication fails, the manager retries individual recording to retain good
evidence. Failed candidates return `inf` with current objective width. Result order
always matches candidate order.

## Invariants

- Local/distributed share job preparation, result, recording, cost, and shape rules.
- Standalone smoke is exactly one midpoint job and has no job/generation timeout.
- Resource retries are bounded fresh clusters for standard memory/disk holds only.
- Submit callbacks run after submission and cannot cancel queued jobs on failure.
- Every stateful lookup uses the effective workspace.
