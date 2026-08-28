# 2026-08-28 20:40 - Make Benchmark A Generic Modular Algorithm Runner

## Context

- The source-checkout benchmark had accumulated a central baseline configuration,
  benchmark-owned strategy assembly, algorithm-specific runners and reports,
  preregistration/evidence trees, duplicated experiment runtimes, and historical
  timing prediction.
- Adding a yadof algorithm therefore required edits in the benchmark product, and
  recovery mixed run-local snapshots with current-checkout configuration.
- The user explicitly authorized the root manual TODO that defined a clean product
  tree and prohibited transitional naming or compatibility surfaces.

## Change

- Reduced `benchmark_automation/` to exactly two root Python files plus
  `baselines/`, `benchmark_runtime/`, `dev_doc/`, and `tests/`.
- Made every baseline self-describing through its own manifest and clean complete
  workspace snapshot. Discovery is recursive and has no central registry.
- Added an external StudyRequest contract for arbitrary complete
  `submit/optimization.py` sources, optional per-baseline sources, seeds, a uniform
  budget, optional reference, failure policy, interpreter, and output root.
- Replaced the runner with one deterministic RunSpec path: plan, driver/input
  snapshot, exact final-cell `yadof check`, shell-free execution, public-yadof
  collection, aggregate publication, and deterministic recovery.
- New runs record a driver digest and copy the complete driver. Resume imports the
  run-owned execution and result modules and does not reload the current study,
  baseline, strategy, or runtime implementation.
- Results now support any number of strategies, preserve unknown public
  optimization metadata opaquely, retain failures, and report evaluation counts,
  success rate, runtime, public objectives, final hypervolume, and optional paired
  reference deltas without algorithm classification or ranking.
- Replaced the command surface with only `baselines`, `plan`, `run`, `resume`, and
  `inspect`; collection and report generation are part of execution/recovery.
- Removed the unused `benchmark` optional dependency and documented the benchmark
  as a source-checkout tool that remains outside wheel and sdist artifacts.
- Rewrote the benchmark developer, architecture, study, run, and baseline guides;
  synchronized root architecture/blueprints/terminology, user guidance, repository
  instructions, and the affected active surrogate research TODOs.

## Removed Product Material

- Removed the root central TOML, local README/AGENTS files, strategy templates,
  specialized experiment runtime and PCA runner, representation dataset settings,
  preregistration/history/verification product directories, timing/state duplicate
  modules, and specialized runner tests.
- Historical meaning remains available in Git and append-only project change
  records; the current product contains no aliases, redirectors, dual readers, or
  generational names.
- Ignored generated caches plus prior `.assembled` and `.staging` evidence were
  moved intact to
  `D:\project\20260414 yadof\20260822 modular\temp\benchmark_cleanup_20260828_194116`
  rather than destroyed.

## Engineering Bounds

- The active CLI, core, and runtime contain 2,000 physical lines in total.
- The largest runtime module contains 362 lines; the largest ordinary function
  contains 78 lines.
- Structural tests reject oversized modules/functions, algorithm-name branches,
  private sibling imports, star imports, incidental generation markers, and product
  tree drift.
- Adding a new algorithm requires only an external complete strategy file and study
  entry; benchmark source, tests, and documentation remain unchanged.

## Validation

- Focused installed-package benchmark suite: `18 passed in 1.15s` using fake child
  commands and a fresh absolute pytest base directory.
- External no-write plan: two previously unknown strategy IDs, two seeds, one
  discovered baseline, four deterministic cells, `writes=false`, no run directory
  created, and a recorded driver digest.
- Wheel build: `yadof-0.4.2-py3-none-any.whl` built successfully and force-installed
  with no dependencies.
- Import origin: `.venv/Lib/site-packages/yadof/__init__.py`, version `0.4.2`.
- Wheel membership: 611 members, with zero benchmark and zero administrator members;
  installed `package_foundation.md` exposes the new source-checkout study contract.
- Full installed-package suite: `368 passed in 77.39s` with disabled cache and a
  fresh absolute pytest base directory.
- No simulator, measured benchmark study, protected dataset, or external campaign
  was started.

## Recurring Checks

- The incidental-release-marker auto TODO triggered in the benchmark scope. All
  in-scope transitional names, aliases, historical help, and numbered current
  surfaces were removed; the recurring TODO remains active.
- The component-configuration migration auto TODO triggered because benchmark
  strategy inputs were in scope. Algorithm settings remain owned only by complete
  external `submit/optimization.py` factories; the runtime gained no second
  configuration entry, and the recurring TODO remains active.
