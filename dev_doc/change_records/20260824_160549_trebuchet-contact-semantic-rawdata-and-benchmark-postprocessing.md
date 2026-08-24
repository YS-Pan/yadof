# 2026-08-24 16:05 - Add Trebuchet Contact, Semantic RawData, And Benchmark Postprocessing

## Context

- Trebuchet result replays showed the throwing arm and counterweight assembly
  passing below the ground plane.
- The task stored several unrelated release and stress curves as artificial
  two-dimensional channel arrays, which obscured their meanings and made each
  joined field a harder surrogate target.
- Benchmark cells retained cost plots but did not provide one uniform hook for
  task-owned human-review plots or videos.

## Change

- Added Bullet NSC contact between the Chrono ground and every moving trebuchet
  body, collision-family filtering that avoids moving-part self-collision, loaded
  geometry rejection, dynamic ground-clearance evidence, and invalid-mechanism
  objective sentinels.
- Replaced the bundled trebuchet rawData arrays with nine scalar fields and seven
  independent 513-sample curve fields; synchronized the job and submit task
  contracts and updated cost extraction.
- Integrated the trebuchet animation renderer and a root `postprocess.py` into new
  immutable Chrono baseline `trebuchet-ac34a09c5fb9`.
- Added the same `postprocess.py --workspace ... --output-dir ...` interface to new
  immutable SAW and test_com baselines. The SAW output follows the 20260807
  response plots; test_com now emits a compact state-response and variable plot.
- Made every measured benchmark cell invoke its baseline postprocessor after the
  cost view, store outputs under one run-level postprocess tree, and fail explicitly
  when postprocessing fails.
- Disabled bytecode writes in runner child processes so ordinary task/postprocessor
  imports cannot add `__pycache__` files and invalidate sealed input fingerprints.
- Documented semantic rawData separation in the user workflow and maintained
  architecture blueprints and benchmark operator guidance.

## Rationale

Explicit rigid-body contact prevents visually and physically invalid mechanisms
from receiving ordinary optimization scores. Independent semantic rawData fields
preserve target identity and let the field-balanced surrogate model each curve
without an invented channel relationship. Keeping visualization logic with each
frozen task while standardizing only its entry point lets the runner automate
human-review artifacts without learning simulator-specific details.

## Impact

- The three prior selected baseline identities remain immutable; the selected
  task fingerprints now include their postprocessors and, for Chrono, the renderer.
- Trebuchet history created with the old bundled rawData contract is not compatible
  with the new baseline.
- Every measured attempt now has an additional required postprocessing phase and a
  unique `postprocess/<cell-id>/attempt-####/` output directory.
- Installed yadof package code did not change, so the package wheel was not rebuilt
  or reinstalled.

## Validation

- A minimal PyChrono drop probe produced zero contacts without an explicit Bullet
  collision system and rested on the ground with four contacts after enabling it.
- Previously penetrating seed 104729 completed with minimum arm, hanger, and
  counterweight clearances of `0.072836 m`, `0.088727 m`, and `0.011326 m`.
- The final midpoint smoke succeeded with four finite costs and exactly 16 rawData
  fields: nine scalars and seven `[513]` curves. All three selected baselines passed
  `yadof check` with zero warnings and their content fingerprints matched metadata.
- SAW, Chrono, and test_com postprocessors each completed in disposable workspaces;
  the final Chrono replay continuation retained a positive minimum counterweight
  clearance of `0.0011768 m`, and its MP4/poster/manifest were generated.
- `pytest benchmark_automation/tests -p no:cacheprovider` passed all 39 tests using
  a fresh external base temporary directory. The Chrono performance preflight
  passed all seven checks for six cells and 12,000 planned evaluations.

## Automatic ToDo Check

- The bounded redundancy review retained the matching job/submit task-spec copies
  because they cross the worker packaging boundary, and retained three task-local
  postprocessors because their selection/rendering contracts differ materially;
  no proven incidental implementation was safe to remove.
- Postprocessors use the public recorded-data readers only after optimization and
  its recording boundary have completed. The runner change does not bypass the
  common finalizer, weaken backpressure, or introduce an alternate recording path.
- Predecessor baseline IDs remain only where immutable provenance must identify the
  exact historical inputs. No in-scope release-transition marker or compatibility
  alias was introduced.

## Follow-Up

Launch the selected Chrono performance benchmark in a detached visible PowerShell
and leave progress inspection to the operator, as required by the benchmark run
contract.
