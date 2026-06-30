# 2026-05-27 20:53 - Worker Declared Resources Script

## Context
- Machine 1 advertised `EXECUTE = R:/condor_execute` but did not define worker `MEMORY` or `DISK`, so it was not usable for jobs that request memory and disk.
- The pool also needs an easy way to let stronger workers run multiple HFSS jobs by using partitionable slots.

## Change
- Added `project/tools/htcondor_pool/setup_worker_declared_resources.cmd`.
- Added `project/tools/htcondor_pool/configure_worker_declared_resources.ps1`.
- The CMD exposes declared CPU, memory, disk, execute directory, restart behavior, and partitionable-slot mode as constants at the top of the file.
- The CMD also exposes the worker Python executable path.
- The PowerShell script writes a managed HTCondor local-config block with `NUM_CPUS`, `MEMORY`, `DISK`, `EXECUTE`, `YADOF_*` attributes, and partitionable-slot settings, grants read/execute access to the configured Python environment for worker slot users, then restarts HTCondor and prints verification output.
- Updated the HTCondor pool README and tools blueprint.

## Rationale
- A double-clickable worker script keeps per-machine resource declaration explicit and repeatable.
- Partitionable slots let a worker split its declared CPU/memory/disk resources across multiple simultaneous HFSS jobs based on each job's `request_*` values.

## Impact
- Run the new CMD on every worker that should execute jobs, including machine 1 if it should act as submit/manager/worker.
- `DECLARE_MEMORY_MB` is written directly as HTCondor `MEMORY`; `DECLARE_DISK_MB` is converted to HTCondor `DISK` in KB.
- The configured `WORKER_PYTHON_EXE` path must exist locally and should match submit-side `HTCONDOR_PYTHON_EXE`.

## Follow-Up
- Tune `DECLARE_*` values per physical machine and keep `project/config.py` job requests lower than the per-worker declared resources.
