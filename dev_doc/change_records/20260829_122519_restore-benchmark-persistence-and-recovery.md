# Restore benchmark persistence, failure, and recovery contracts

## Context

Section 8 of
`dev_doc/toDo/20260829_081608_restore-benchmark-ux-and-testing-contract.md`
combined the reliable yadof recorder boundary with benchmark-level failure,
attempt, snapshot, and Windows recovery behavior. The code-first runner already
kept run-owned inputs and compact workspaces, but structural workflows did not
default to fail-fast, collected-but-invalid cells could still finish successfully,
and attempt sealing/publication failure lacked explicit durable contracts.

## Changes

- `Benchmark.configure()` now defaults failure scheduling by evidence class:
  structural workflows fail fast, while performance workflows continue independent
  cells. An explicit override changes scheduling only; final success still requires
  every cell to be complete and valid.
- Aggregate result/report/index publication is a synchronous boundary before the
  next cell. A publication/storage exception stops the campaign, emits a diagnostic,
  persists a bounded failure record when state storage remains available, and
  propagates as `BenchmarkError`.
- Cell and postprocessor attempts now publish independent `attempt.json` metadata.
  Failed/interrupted execution is sealed incomplete, collected work is sealed
  complete, and sealed metadata cannot be changed. Execution retry creates a new
  numbered attempt and compact workspace without overwriting earlier evidence;
  collection-only retry reuses successful open execution evidence.
- Execution revalidates the run-owned driver, workflow/resources, baseline, and
  strategy digests. Editable source changes therefore affect new runs while
  mutation inside an existing snapshot fails closed. Baseline digesting now
  excludes nested `.yadof` runtime state consistently with clean snapshot copying.
- Package/root terminology, architecture, blueprints, user/developer guides, tests,
  and the active restoration TODO now state the restored section 8 boundary.

## Verification

- Built `yadof_benchmark-0.1.0-py3-none-any.whl`, force-reinstalled it into the
  outer workspace `.venv`, and confirmed `yadof_benchmark` and `yadof` import from
  that environment's `site-packages`.
- Focused installed-package recovery tests: 5 passed.
- Full installed-package benchmark suite: 44 passed with source injection disabled,
  a fresh absolute pytest base temp, and the cache provider disabled.
- Existing yadof recorder durability/backpressure suite: 25 passed.
- No simulator, adapter smoke, or performance campaign was executed; all benchmark
  execution tests used fake commands and synthetic public-result fixtures.
