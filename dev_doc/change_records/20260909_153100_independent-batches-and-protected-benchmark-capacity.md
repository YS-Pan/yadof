# Independent evaluation batches and protected benchmark capacity

The optimizer previously tied retained population P to every real-evaluation
batch. Long surrogate studies also underused available workers, while increasing
parallel processes on Windows could exhaust committed memory despite low resident
RAM. Single-seed perfect-surrogate crossings were too narrow for the next studies.

## Completed changes

- Added independent positive B and I settings to the public API, CLI and config.
  Defaults remain B=I=P. GA/NSGA-III retain P, evaluate I initially and B thereafter;
  GPSAF and posterior selection use the actual real-batch quota. Explicit program
  stopping owns long history replay. Surviving individuals reuse their evaluation;
  recorded_data, view-cost and formal-budget counts do not duplicate survivors.
- Added exact zero-gain shortcuts to greedy HV and optional parallel amplitude-GP
  field fits, with private writable field buffers, ordered outputs, bounded native
  threads, and cancellation that joins all workers. These preserve checked outputs.
- Enabled dependency-aware parallel top-10 benchmark cells and P/B/I budgets,
  paired-reference validity, censored crossing quantiles and budget-aware progress.
  Transient Windows atomic replacement conflicts receive bounded retries; fatal
  storage/resource failures cancel peers and retain the primary error.
- Applied native numerical thread limits before child imports. Windows command
  trees share a private-commit budget and an independent system-memory watchdog;
  resource exhaustion stops admission regardless of `fail_fast`. No system
  page-file or ACL configuration is changed.
- Corrected Chrono's launch-directory limit to 258 UTF-16 units and synchronized
  its benchmark adapter. Collection rejects explicit nonphysical infrastructure
  failures so a partly broken reference cannot appear easier to beat.
- Calibrated remaining formal cells in small rolling cohorts. General defaults
  are four cell slots, with per-cell physical-core multipliers Chrono1, SAW2 and
  antenna1. The internal calibration hook only changes future execution capacity;
  user docs explain the two existing configuration controls and simple usage.
- Published 27 five-seed perfect P/B distributions with exact per-seed data,
  reference values, median, quartiles and censored outcomes. Old perfect MD/PNG and
  the long CAE development log were archived byte-for-byte. Active CAE context now
  retains research lessons, and H26's closure retains historical outcomes without
  promoting its superseded perfect gates to current thresholds.

## Verification and evidence

Core installed-wheel regression: **574 passed**, two expected GP convergence
warnings, **156.99 s**; the resident/subprocess subset passed **23 tests, 7.40 s**.
Final independent benchmark installed-wheel regression: **95 passed, 23.94 s**.
Both import origins resolve under the selected environment's site-packages.
Subsequent core documentation changes use the content-only validation exception,
with a wheel refresh for immediate packaged-document visibility.

The controlled 12-cell fixed-input speed comparison reduced complete wall time
from 1194.986 to 591.115 seconds (**2.022x**) with identical formal trajectories,
design/cost fingerprints and oracle correspondence. Field-fit and HV timings are
reported separately rather than presented as full-workflow speedups. Limiting
native pools reduced single cold-import private commitment by **96.26%**; this is
not a claim of the same percentage for a complete benchmark.

The revised study contains **150 independently audited formal cells**, five seeds
for each of 27 case/P/B combinations: **455,740 formal attempts**, **449,647 finite**,
**6,093 failed/nonfinite**, plus **1,505,196 separately counted oracle queries**.
Retained partial workspaces contribute only whole audited case/seed groups.
Commit-exhaustion and Chrono launch failures remain preserved and excluded as
specified before pooling. Perfect queried-pool predictions are an empirical
comparator, not a mathematical upper bound on every search trajectory or metric.

- [P/B, throughput, memory and installed acceptance context](../context/20260908_224400_population-batch-and-throughput-validation.md)
- [Five-seed perfect-surrogate P/B baseline](../context/20260909_152719_five-seed-perfect-surrogate-pb-baseline.md)
- [Benchmark execution contract](../../yadof-benchmark/user_doc/execution.md)

The shared checkout's earlier preparation concurrency fix and H26 closure were
already in source HEAD `6c95eb2a5cddc5eff3e03727c6566bf20c401ba6`; they were
preserved. Experimental H26 algorithms were not integrated or declared accepted.
