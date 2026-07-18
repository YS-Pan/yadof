# 2026-07-18 15:28 - Package Local Evaluation And Smoke

## Context

- Installed workspaces could be initialized and checked, but running a workflow
  still depended on the repository `project/` tree.
- Package step 4 required immutable worker support to compose safely with mutable
  workspace tasks, with no package writes, source-root imports, or authoritative
  cost artifacts.

## Change

- Migrated the old local evaluator/job-result/job-preparation shapes and
  `project/job_template/worker_misc.py` by copying them into
  `src/yadof/evaluate_manager/` and adapting the copies to explicit workspace/config
  APIs and package-relative imports.
- Added collision-safe task/package composition, complete adapter/asset copy,
  assigned parameter snapshots, definition-only static hashing, compact effective
  worker config, and yadof/workspace/task provenance.
- Added local subprocess rawData validation, process-tree timeout, per-individual
  failure isolation, dynamic current-workspace cost return, and enforcement that
  workflows cannot leave `cost.json`.
- Added `yadof smoke-test --workspace PATH --mode local [--real-task]`: exactly one
  deterministic midpoint individual with no timeout, with an exact-template safety
  gate before edited or external task execution.

## Rationale

- Copying the mature local runner and worker helper preserved proven lifecycle,
  termination, and metadata techniques while removing repository assumptions.
- Exact reserved-name errors and exact generic-template detection avoid silent
  overwrites and unsafe guesses about whether a workflow is cheap.
- Compact JSON gives workers enough effective context for diagnosis without copying
  package config source or turning installed resources into mutable state.

## Impact

- New installed Python APIs are available under `yadof.evaluate_manager`; the
  source `project.evaluate_manager` remains only for the transitional optimizer,
  recording, and distributed path.
- New local jobs live under the selected workspace and contain task payload,
  package worker support, rawData, and metadata but not submit-side cost code.
- Architecture, module blueprints, terminology, root/project/test READMEs, and user
  workflow/config/package/adapter documents now describe the packaged local path.
- Focused tests cover contents, adapters/assets, collisions, assigned values,
  hashing, provenance, successful/failed/timed-out local jobs, and smoke safety.
  Artifact integration proves the same paths from an installed wheel outside the
  repository with site-packages non-writable and unchanged.

## Follow-Up

- Package step 5 migrates durable recorded data and will connect packaged local
  results to workspace history. Optimization, tools, and distributed execution
  remain in their later ordered stages.
