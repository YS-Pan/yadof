# 2026-08-24 11:23 - Recalibrate the test_com benchmark baseline

## Context

The first 100-by-20 benchmark exposed nearly horizontal cost histories and final
hypervolume near `1e-4` for the synthetic `test_com` case. A 100,000-sample audit
showed that task-owned measurement windows and physical anchors compressed all four
objectives into soft-cost tails even though the adapter rawData remained responsive
to the 20 parameters.

## Change

- Added immutable baseline `synthetic-antenna-c7b0133b3a4e` and selected it in
  `benchmark.toml`; retained the old identity unchanged as historical provenance.
- Replaced the task’s S11, gain, back-lobe, and axial-ratio interpretation with
  state-aligned measurements and fixed physical anchors spanning the useful
  synthetic response range.
- Updated benchmark baseline/status documentation and added a tracked verification
  record with the diagnosis, static audit, and three complete real-only runs.
- Kept the packaged and baseline-copied `test_com.py`, parameters, evaluator,
  rawData shapes, workflow, and four-objective width unchanged.

## Rationale

The defect was task-specific objective policy, not a reusable adapter or framework
mechanism. Keeping the correction in `submit/calc_cost.py` preserves the
task/framework boundary and makes the new identity reproducible without changing
the simulator stand-in used by other workspaces.

## Impact

Future benchmark runs use a non-degenerate synthetic antenna problem. Existing run
reports remain valid only for their frozen old baseline and must not be compared
directly with new-baseline results. Three pure NSGA-III validations, each with 100
individuals for 20 generations, recorded all 2,000 rows and reached final HV
`0.8833`, `0.8597`, and `0.8681`.

## Follow-Up

The full two-arm benchmark has not been rerun as part of this baseline repair.
Future algorithm comparison should create a new run identity using the selected
baseline and should retain the normal paired-seed validity checks.
