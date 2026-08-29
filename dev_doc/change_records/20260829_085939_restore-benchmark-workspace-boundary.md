# 2026-08-29 08:59 - Restore benchmark workspace boundary

## Context

- The code-first rewrite retained the independent package and most of the workspace
  model, but the initialized `benchmark.py` omitted postprocessing and used a
  role-only `reference` example instead of an algorithm identity.
- Baseline discovery trusted each manifest ID without requiring the editable source
  directory itself to use the same provider/task semantic path. That allowed the
  old opaque-fingerprint naming failure to reappear even though current packaged
  baselines happened to be named correctly.
- The first subsection of the active benchmark-restoration TODO requires the
  independent Python-only package, one discoverable workflow entry, semantic
  strategy and baseline naming, editable baseline sources, and immutable run
  snapshots. Later output, progress, ETA, performance, metric, recovery, and
  parallelism requirements remain separate work.

## Change

- Expanded the initialized `benchmark.py` scaffold so its single entry visibly
  covers run policy, a semantically named complete strategy, baseline selection,
  seeds, budget, and a top-level postprocessor.
- Required every discovered baseline manifest directory relative to the selected
  collection root to equal its semantic ID, such as `ngspice/saw-ladder`.
- Replaced role-only strategy examples in user documentation with `nsga3` and
  `gpsaf-conditional-inr`, documented editable external baseline collections and
  run-time freezing, and synchronized benchmark/root architecture, blueprint, and
  terminology contracts.
- Removed a redundant source-token scan that only proved deleted workflow surfaces
  remained absent, plus the duplicate-ID branch made unreachable by the exact
  semantic-path invariant. Observable public API, CLI, distribution entrypoint,
  scaffold, and baseline path behavior retain direct tests.

## Rationale

- A user or AI agent should understand the complete workflow by opening
  `benchmark.py`, without reconstructing algorithm identity or postprocessing from
  comparison roles and external conventions.
- Semantic source paths remain readable while a run's digest and complete snapshot
  provide the needed immutability. Provenance therefore does not leak into editable
  directory names.
- The package remains algorithm-agnostic: it validates structure and source
  identity but does not maintain a registry or infer algorithm meaning.

## Impact

- Existing packaged baseline paths already satisfy the new discovery invariant.
- Custom collections with a manifest stored below a path different from its ID now
  fail before planning or run creation and must be renamed; no run evidence is
  modified.
- No TOML workflow, compatibility alias, release-stage name, algorithm registry, or
  simulator execution was introduced.

## Validation

- Built `yadof_benchmark-0.1.0-py3-none-any.whl`, force-reinstalled it without
  dependencies, and confirmed imports from
  `.venv/Lib/site-packages/yadof_benchmark`.
- Installed-package benchmark suite: `14 passed in 1.03s` with source injection
  disabled, the pytest cache disabled, and a fresh absolute base temp directory.
- Installed CLI discovery returned the three semantic packaged baseline IDs, and
  installed `docs show` exposed the updated strategy and editable-baseline
  contracts.
- An external one-cell structural plan using a complete `nsga3` strategy returned
  `writes=false`; its `runs/`, `reports/`, and `visualizations/` directories
  remained empty. No simulator or measured campaign ran.

## Recurring Checks

- The in-scope redundancy check found the source-token scan and now-unreachable
  duplicate baseline-ID branch. Their removal touched only the implementation and
  direct test module. The three code/test files total `43` added and `26` removed
  lines because the restored scaffold and behavior tests add the requested
  contract; the redundancy cleanup itself removed about 16 lines.
- The incidental release-marker check removed active wording about former entry
  files, migration surfaces, legacy layout, and the corresponding historical test
  name. Real protocol versions and append-only history were retained. Both
  recurring automatic toDos remain active.

## Follow-Up

- Subsections 2--9 of the active benchmark-restoration TODO remain pending and are
  intentionally not claimed by this change.
