# 2026-08-03 17:30 - Add Fast Evaluation Mode

## Context

- The existing local and distributed backends materialized a durable job directory
  for every candidate before recording rawData.
- Fast single-host simulations needed a lower-overhead path without sacrificing
  process isolation, hard timeouts, evidence-first cost calculation, or recording
  integrity.

## Change

- Added `fast` as an explicit third evaluation backend across configuration, API,
  CLI run and smoke-test commands, and workspace checks.
- Added a reusable, replaceable spawn-process worker pool with resource-bounded
  concurrency, per-candidate scratch directories, process-tree observation,
  timeout/crash isolation, descendant cleanup, and ordered population results.
- Added the shared `job_template/evaluation.py` task-kernel contract and extracted
  pure in-memory parameter assignment from prepared-job materialization.
- Extended backend-neutral results and recorded-data ingestion to accept validated
  named in-memory rawData items and atomically encode them into the existing
  archive before calculating current costs.
- Added focused integration coverage for parallel and out-of-order completion,
  local/fast kernel equivalence, real subprocess execution and failure, worker
  crashes, hard timeouts, process-tree cleanup, contract errors, CLI smoke tests,
  and cross-workspace isolation.
- Updated architecture, blueprints, terminology, and user guidance for the new
  backend and its scratch/resource/task contracts.

## Rationale

- A dedicated backend keeps fast execution free of durable per-job artifacts while
  preserving the same authoritative chain from normalized variables through
  recorded rawData to dynamically calculated costs.
- Processes, rather than in-process threads, contain native crashes and permit the
  parent to replace a failed worker and continue the remaining population.
- A single parent-side recorder preserves existing archive locking, atomic update,
  recovery, and manifest semantics while bounded worker pipes provide backpressure.

## Impact

- Fast-compatible workspaces may select `EVALUATION_MODE = "fast"` and implement
  `evaluate_rawdata(parameters, context)` without creating entries under `jobs/`.
- Local and distributed behavior remains unchanged; ordinary workflows may reuse
  the same task kernel through their prepared-job adapter.
- Fast scratch is temporary rather than durable evidence. Cleanup failures and
  worker/simulator diagnostics are retained in recorded metadata.

## Follow-Up

- None.
