# 2026-05-21 08:20 - Local Evaluation Parallelism

## Context
- Local evaluation previously prepared, ran, and recorded each individual sequentially.
- Pure-Python workflows can safely use more than one local subprocess, while real simulator adapters may need sequential execution because of licenses, COM state, or application-level limits.

## Change
- Added `LOCAL_EVALUATION_MAX_WORKERS` to `project/config.py` and `project.evaluate_manager.config`.
- Updated local `evaluate_population()` so individuals can run concurrently through a thread pool when the worker count is greater than 1.
- Preserved per-individual failure isolation and population-order cost return.
- Made prepared job directory creation resilient to concurrent name collisions.

## Rationale
- Local mode should be able to use available workstation capacity for parallel-safe workflows without requiring HTCondor.
- Keeping the default worker count at 1 preserves old behavior for simulator-backed tasks until the user explicitly opts into parallelism.

## Impact
- Users can set `LOCAL_EVALUATION_MAX_WORKERS` above 1 to run multiple local workflow subprocesses at once.
- Durable `recorded_data` writes still serialize through the existing metadata/rawData archive lock.
- Existing local and distributed API shapes remain compatible.

## Follow-Up
- Tune worker counts per task, especially for real simulator adapters that may have process, license, or file-lock constraints.
