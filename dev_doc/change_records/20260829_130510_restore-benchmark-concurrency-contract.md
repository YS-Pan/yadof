# Restore benchmark concurrency and resource contracts

## Context

Section 9 of
`dev_doc/toDo/20260829_081608_restore-benchmark-ux-and-testing-contract.md`
requires explicit cell and simulation concurrency without turning an historical
8-core/32-simulation example into a universal default. Higher utilization must
remain bounded by simulator, memory, license, recorder, and current yadof resource
contracts and cannot weaken budgets, durability, failures, progress, or ETA.

## Changes

- `Benchmark.configure(cell_concurrency=...)` now freezes a positive workflow-wide
  cell limit with safe default one. Cells enter a bounded FIFO scheduler; initial
  slots may overlap, but a terminal cell publishes aggregate evidence before its
  freed slot admits the next waiting cell.
- Fast/local baseline manifests now explicitly freeze `simulation_concurrency`
  with `max_workers` and `resource_autodetect`. Attempt materialization writes the
  corresponding yadof settings into the run-owned config and records the resolved
  choice in `attempt.json`.
- Shared state publication is serialized across cell workers. Worker lifecycle and
  child-progress events are queued back to the foreground caller, storage failure
  is campaign-fatal, and fail-fast cancels active default subprocesses and blocks
  new admission.
- Read-only ETA now models configured concurrency lanes: active cells preload lanes
  and queued FIFO cells fill the earliest available lane. Bounded plan/check output
  exposes both concurrency layers.
- Packaged baseline caps remain task-specific and resource-autodetected. Explicit
  oversubscription remains possible by author choice but requires combined
  simulator/license/memory/recorder/host review.
- Developer/user documentation, architecture, terminology, blueprints, structural
  tests, and the active restoration TODO now state the concurrency contract. A
  duplicated benchmark-metrics paragraph in the touched development-view document
  was removed as an in-scope documentation redundancy.

## Verification

- The implementation is covered by fake-command structural tests for plan
  validation/freezing, run-owned materialization, bounded overlap, FIFO admission,
  publication-before-refill, foreground event delivery, unchanged budgets,
  storage-fatal behavior, and lane-aware ETA.
- Built `yadof_benchmark-0.1.0-py3-none-any.whl`, force-reinstalled it into the
  outer workspace `.venv`, and confirmed `yadof_benchmark` and `yadof` import from
  that environment's `site-packages`.
- Full source and installed-package benchmark suites each passed 47 tests with a
  fresh absolute pytest base temp and the cache provider disabled.
- An installed CLI `plan` from a fresh external temporary study reported
  `cell_concurrency=2`, the packaged simulation cap, `writes=false`, exit 0, and
  left all three input files byte-identical with no added file. The workflow
  loader now disables bytecode writes, with direct regression coverage.
- No simulator, adapter smoke, or performance campaign is authorized or executed
  by this change.
