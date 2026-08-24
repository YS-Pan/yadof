# 2026-08-24 19:58 - Unify Benchmark Visualizations And Prune Old Baselines

## Context

- A measured benchmark attempt wrote its yadof cost plot below the copied cell
  workspace while the task-owned postprocessor wrote plots and videos below a
  separate run-level tree.
- Human and agent inspection therefore needed two unrelated paths for one result.
- Superseded SAW, Chrono, and test_com baseline workspaces remained beside the
  selected identities after their replacements had been validated.

## Change

- Added one runner-owned
  `<run-root>/visualizations/<cell-id>/attempt-####/` directory for every measured
  attempt.
- Made the runner call the baseline `postprocess.py` with that new empty directory,
  then pass its absolute `benchmark-cost.png` path to `yadof view cost` so all
  task-specific and generic visualization artifacts are colocated.
- Renamed the attempt-state output field to `visualization_output_dir`, updated
  planned commands, tests, architecture, operator guidance, and the output tree.
- Derived immutable Chrono baseline `trebuchet-20167c28925b` from
  `trebuchet-ac34a09c5fb9` to freeze the new visualization usage instructions; the
  contact-aware model, semantic rawData contract, and renderer are unchanged.
- Removed two superseded Trebuchet baselines, one superseded SAW baseline, and
  three superseded test_com baselines at explicit maintainer request. Each provider
  now contains only the baseline selected by `benchmark.toml`.

## Rationale

A single per-attempt directory gives each optimization result one stable place for
cost history, task plots, videos, manifests, and supporting evidence without file
name collisions across cells or retries. Running the task postprocessor first
preserves its empty-output-directory contract; the generic cost plot can then be
added to the same directory. Deriving a new Trebuchet identity preserves baseline
immutability when its packaged usage instructions change.

## Impact

- New measured attempts expose all visualizations below `visualizations/` instead
  of splitting them between `postprocess/` and `.yadof/tool_output/`.
- Either task postprocessing or cost rendering remains a required phase whose
  failure fails the immutable attempt.
- Historical run specifications and verification records still name removed
  baseline identities, but those runs cannot be resumed or reconstructed from
  this checkout without restoring the deleted directories from Git history.
- Installed yadof package code did not change, so no wheel rebuild or reinstall was
  required.

## Validation

- The benchmark Python sources parsed successfully and the benchmark unit suite
  passed all 39 tests with a fresh external pytest base temporary directory.
- A Chrono performance plan resolved six measured cells and 12,000 planned
  evaluations; a focused full-JSON structural plan showed both measured cells
  passing the exact same visualization directory to postprocessing and cost view.
- The complete three-case `structural-full` preflight passed all 13 checks,
  including all baseline fingerprints, three `yadof check` calls, ngspice,
  PyChrono, CUDA, both strategy templates, disk space, and the installed package.
- A real recorded SAW workspace produced `saw_best_response.png`, SVG, CSV,
  `postprocess_manifest.json`, and `benchmark-cost.png` together in one validation
  output directory without launching a simulator.
- The Chrono task fingerprint recalculated as
  `20167c28925bd9ff0e0476cb305e1f258a57dfd9098ea6e5afc44b61cee0b306`, matching
  its directory prefix and manifest, and each provider directory contains exactly
  its selected baseline.

## Automatic ToDo Check

- The output directory and cost filename are runner constants recorded once per
  attempt; no parallel legacy output path or compatibility alias was retained.
- Both visualization commands run only after optimization, generation validation,
  and any declared extension. The change does not alter evaluation finalization,
  recorder backpressure, history, or checkpoint publication.
- Removed identities remain only where provenance must name historical inputs.
  There is no in-scope release-transition marker or temporary implementation left
  to remove.

## Follow-Up

No additional benchmark execution is required for this path and baseline cleanup.
