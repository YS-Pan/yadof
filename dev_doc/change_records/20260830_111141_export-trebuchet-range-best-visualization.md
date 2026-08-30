# 2026-08-30 11:11 - Export Trebuchet Range-Best Visualization

## Context

- The packaged Chrono trebuchet baseline postprocessor exported only the completed
  optimization individual with minimum arithmetic-mean objective cost.
- Users also need a direct visualization of the individual that optimizes throw
  range, represented by the task's `cost_range` minimization objective.

## Change

- The trebuchet postprocessor now scans eligible completed history once and selects
  both the minimum-average-cost individual and the minimum-`cost_range` individual.
- The original average-best filenames and manifest fields remain available. A
  second range-best video, poster, selected-job archive, continuation diagnostic,
  and animation trajectory are exported with `trebuchet_range_*` names.
- The manifest schema is now version 2 and records the range selection rule,
  selected evidence, and artifact paths. Both renders remain visualization-only
  and add no optimization evaluation or history record.
- Focused benchmark tests cover distinct average/range winners, invalid-row
  filtering, two renderer invocations, both artifact sets, and manifest content.

## Rationale

- Average objective cost is useful for reviewing a balanced compromise, while the
  range objective directly identifies the farthest throw. Exporting both avoids
  making users reconstruct or rerun a cell to inspect the range extreme.
- Reusing one selection pass and one rendering helper keeps both exports under the
  same snapshot, validation, continuation, and atomic-copy contracts.

## Impact

- The independent `yadof-benchmark` wheel's Chrono trebuchet baseline resources,
  focused structural tests, and task visualization documentation changed.
- Generic benchmark planning, execution, validity, and postprocessor invocation
  contracts are unchanged.

## Follow-Up

- No measured benchmark or real PyChrono continuation was run as part of this code
  change; structural tests use a fake renderer, while the baseline workspace check
  validates the task definition without executing the simulator.
