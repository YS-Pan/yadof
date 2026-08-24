# 2026-08-24 20:17 - Flatten Benchmark Visualization Output

## Context

- The first unified visualization implementation still placed each cell attempt
  below `visualizations/<cell-id>/attempt-####/`.
- The requested contract is stricter: every visualization result from one benchmark
  run must be a direct child of one directory, with no cell/attempt result
  subdirectories.
- Existing task postprocessors used fixed names and rejected nonempty directories;
  Trebuchet additionally retained `selected_job/` and `_animation_work/` trees.

## Change

- Made every measured cell share `<run-root>/visualizations/` and moved cell/attempt
  identity into the collision-safe filename prefix
  `<cell-id>__attempt-####__`.
- Added `--output-prefix` to the common postprocessor interface. SAW, Trebuchet, and
  test_com apply it to every persistent artifact, allow unrelated files in the
  shared directory, and refuse to overwrite any matching output name.
- Made `yadof view cost` write `<prefix>benchmark-cost.png` directly beside the
  task-owned files. The attempt state now records both the shared directory and its
  unique prefix.
- Replaced Trebuchet's persistent output subdirectories with prefixed flat files:
  the selected job is archived as ZIP, continuation diagnostics and trajectory are
  copied out as named files, and animation scratch uses an automatically removed
  temporary directory.
- Derived and selected immutable baselines `saw-ladder-3d2025426a97`,
  `trebuchet-42e80c54ebb5`, and `synthetic-antenna-0b64f13b9f0b`; their scientific
  task definitions are unchanged. Removed their three superseded directories at
  explicit maintainer request so every provider still contains one workspace.
- Updated operator instructions, architecture, baseline provenance, the output
  tree, and focused unit coverage for the flat contract.

## Rationale

One flat directory makes the complete visual result of a benchmark run directly
browsable and exportable. Encoding identity in filenames prevents collisions
across cases, arms, seeds, and retries without reintroducing directory hierarchy.
Keeping Trebuchet scratch temporary and archiving its reproducible snapshot retains
useful evidence while satisfying the no-subdirectory result contract.

## Impact

- New runs write every visualization file directly under `visualizations/`; no
  cell/attempt directories are created there.
- Consumers must locate an attempt through its filename prefix rather than a nested
  path. Postprocessing and cost-view failures still fail the immutable attempt.
- Historical runs using removed baseline identities cannot be resumed from this
  checkout without restoring those inputs from Git history.
- Installed yadof package code did not change, so no wheel rebuild or reinstall was
  required.

## Validation

- The benchmark test suite passed all 42 tests, including new tests that write two
  SAW cells into one nonempty directory, flatten test_com output, and verify that
  Trebuchet produces only files plus a readable selected-job ZIP.
- A real recorded-data integration wrote two SAW postprocess results, one test_com
  result, and one yadof cost plot into one directory: 11 files and zero
  subdirectories.
- The final three-case `structural-full` preflight passed all 13 checks, including
  all baseline fingerprints, three `yadof check` calls, ngspice, PyChrono, CUDA,
  both strategies, disk space, and the installed package.
- A full-JSON Chrono plan showed both measured arms sharing
  `<run-root>/visualizations` while using distinct prefixed postprocess and cost
  filenames.
- Final task fingerprints are
  `3d2025426a976aa03cf720757bd37314004db8d29b5a922dcfc36c2d0d753c10`,
  `42e80c54ebb54872b62961babe4095b6c2601eae9b2393ddc39d3950ed9b7cc9`, and
  `0b64f13b9f0b209f5dd23ce4d7f841119580f47885536db2184cb661d6c088f8`.

## Automatic ToDo Check

- The runner records one shared directory and one unique prefix per attempt; no
  legacy per-cell visualization path or redundant naming source remains.
- Visualization still begins only after optimization, completed-generation
  validation, and any declared extension. Evaluation finalization, recorder
  backpressure, history, and checkpoints are unchanged.
- Superseded IDs remain only in historical provenance. No compatibility alias,
  transition branch, or temporary result-directory implementation remains.

## Follow-Up

No additional optimization run is required for the flat-output contract.
