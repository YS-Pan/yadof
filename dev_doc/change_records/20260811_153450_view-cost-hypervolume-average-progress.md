# 2026-08-11 15:34 - Add View-Cost Hypervolume, Average, And Progress

## Context

- The summed `Combined cost` occupied the cost plot's right axis even though its
  objective-count scaling made its screen height equivalent to an arithmetic mean
  on the left axis.
- Users needed the right axis for both cumulative-all-individual and
  current-generation hypervolume, with the difference visible as a shaded band.
- Dynamic reinterpretation of large recorded histories left the terminal blank
  long enough to look stalled.
- `temp/20260811 from 2sc1970/viewCost.pyw` provided an older-branch cumulative-HV
  prototype but came from a different pre-package tool architecture.

## Change

- Replaced summed `Combined cost` with arithmetic `avg. cost`, including the
  summary table, points, and smoothed trend, all on the left cost axis.
- Added fixed-reference `(1, ..., 1)` minimization hypervolume at each contiguous
  run/generation endpoint. The right axis draws cumulative all-individual and
  current-generation boundaries and shades between them; rows outside `[0, 1]` do
  not contribute to HV.
- Reused one contiguous-generation grouping result for both generation backgrounds
  and hypervolume membership.
- Added optional historical-query progress callbacks and an automatic bounded CLI
  progress bar on stderr for normalization, rawData loading, and dynamic cost
  calculation.
- Updated tests, user guidance, architecture, terminology, and module/file
  blueprints.

## Rationale

- `sum(costs) / objective_count` on the left axis has exactly the same vertical
  position as the old summed value on an objective-count-scaled right axis, so the
  semantic rename does not introduce a visual jump.
- A fixed normalized reference keeps HV comparable across generations and avoids
  adapting the metric to the observed history.
- The reference implementation's `pymoo.indicators.hv.HV` use, unit reference, and
  exclusion of out-of-range normalized costs were applicable. Its legacy GUI, CSV,
  package-bootstrap, and plot-layout behavior were not. It contained no applicable
  cost-calculation acceleration, so none was copied.
- Progress belongs on stderr so stdout remains a clean summary/API capture surface.

## Impact

- `yadof view cost` and the cost portion of `yadof view all` display progress and
  produce the new average/HV plot.
- `recorded_data.api.get_historical_results()` accepts an optional progress
  callback; callers that omit it retain the prior return value and quiet behavior.
- The `20260807 saw` workspace rendered 4,997 usable rows with five objectives and
  no ignored issues, producing the expected two HV boundaries and shaded band.

## Follow-Up

- None.
