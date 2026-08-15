# 2026-08-15 16:51 - Unify Loss-Tolerant Evaluation Recording

## Context

- Fast evaluation recorded inline while local/distributed evaluation used a
  batch/fallback path over one growing JSONL/global ZIP. Recording exceptions could
  affect valid results and every append rewrote campaign-scale state.
- The explicitly requested
  `20260813_165610_unify-loss-tolerant-evaluation-recording.md` contract permits an
  incompatible segmented format and requires current cost to remain independent of
  best-effort persistence.
- The migrated checkout also contained two environmental/source artifacts: the
  source/test directories deny some cache/temp creation, and `fast_runner.py`
  contained a duplicated `slot.connection.send(request)` absent from the supplied
  older package tree.

## Change

- Added a generation-scoped task snapshot with stable parameter/objective capture,
  complete task identity, and separate dependency-aware interpretation/evaluation
  fingerprints. Fast, local, distributed, current-cost, and asynchronous surrogate
  work use one copied generation tree.
- Added one backend-neutral `JobResult` finalizer. It validates and owns file- or
  memory-backed rawData, calculates current cost, returns that cost, and only then
  makes a non-blocking recorder offer. Invalid rawData/cost remains an evaluation
  failure; every later recording failure is isolated from the result.
- Replaced mutable global history with immutable standard-ZIP segments. Each
  same-run/generation micro-batch has candidate-scoped metadata/NPZ members and a
  manifest written last, then publishes through a same-directory atomic
  rename. Existing segments are never reopened.
- Added one explicit `CampaignSession` with an OS workspace lock, one bounded daemon
  writer, exact candidate/byte admission accounting, generation-boundary flush,
  isolated write failure, consecutive-failure circuit breaker, writer-death
  containment, bounded shutdown, and monotonic recording-loss counters.
- Made the session's startup segment catalog plus accepted current rows the hot
  history used by optimization, resource calibration, and surrogate training.
  Interpretation edits rebuild derived variables/costs; evaluation-only edits reuse
  them. Dropped rows remain useful only until reinterpretation requires unavailable
  evidence.
- Converted public history queries, viewers, surrogate recovery/training, resource
  planning, optimization metadata, and history clear to segmented storage. Readers tolerate bad
  candidates/segments and report bounded diagnostics. History clear refuses an
  active campaign and deletes only framework-owned segment and event directories.
- Deleted the old JSONL/global-ZIP readers, writers, backend client, and compatibility
  tests. Legacy files are neither inspected nor deleted.
- Removed the migrated duplicate fast-worker request send. The persistent automatic
  redundancy task remains active after this bounded occurrence.

## Reliability And Performance Evidence

- Added parameterized count/byte-budget tests, float32/float64
  `10 * 360 * 360` singleton publication, file/memory equivalence, non-blocking
  oversize loss, write recovery, circuit breaker, unexpected writer death, blocked
  shutdown, lock retention, two-workspace independence, temporary/corrupt segment
  recovery, candidate CRC loss isolation, and proof that new publication never
  opens an older segment.
- Added generation reload tests for cost and parameter reinterpretation,
  evaluation-only cache reuse, copied non-Python inputs, and campaign-frozen
  recorder configuration.
- On this Windows/Python 3.13 environment, the synthetic 100,000-candidate catalog
  test completed in about `0.21 s`. The 5,000-row startup-catalog regression plus
  100 current finalizations completed in about `0.32 s` without a history scan per
  finalization. These are regression observations, not hardware-independent
  latency promises.
- Source-tree and installed-wheel suites both completed with `234 passed`; warnings
  are the expected rate-limited recording-loss warnings from fault-injection tests.
- Built `yadof-0.2.0-py3-none-any.whl`, force-reinstalled it into the current
  workspace `.venv`, verified imports resolve from `site-packages`, and reran the
  complete suite against that installed package.

## Migration Observation

- The migrated repository cannot create normal source `__pycache__` and default
  pytest temporary paths under some directories. Tests therefore use an explicit
  writable outer `--basetemp`. The first normal wheel reinstall also hit access
  denied on the existing `.venv` dist-info and succeeded only with elevated access.
  This is an environment ACL migration issue rather than a yadof behavior failure;
  no broad permission rewrite was attempted.

## Impact

- Newly recorded evidence uses only `recorded_data/segments/`; old history does not appear
  in new queries and requires an explicit external migration if ever needed.
- Valid evaluation costs and optimizer progress no longer depend on history
  publication. Recent best-effort history may be lost within the configured
  unpublished bounds on overload, storage failure, or process exit.
- One workspace now rejects overlapping campaigns and destructive history clear
  through an OS-backed lock. Different workspaces remain independent.
- Shape-preserving task edits take effect coherently at the next generation;
  parameter identity/count and objective count remain campaign-stable.

## Follow-Up

- Consider repairing the migrated checkout/virtual-environment ACLs outside this
  code change so ordinary cache/temp creation and future package reinstalls do not
  require workarounds.
- Add an index only if later measurements at or below the documented 100,000-row
  horizon show a real startup/viewer bottleneck.
