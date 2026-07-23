# File blueprint: src/yadof/tools/view_cost.py

## Intent

- Turn one workspace's recorded raw evidence into a current-cost text summary and
  optional static PNG without persisting cost as authoritative history.

## Functionalities

- Read historical results through `recorded_data.api.get_historical_results()` so
  costs are recalculated by the current task.
- Merge individual and optimization metadata to annotate optimization starts,
  generation/run identity, and static-input hash changes.
- Validate finite numeric variables/costs and one consistent objective width.
- Obtain task objective names when their count matches, with deterministic generic
  fallbacks.
- Identify the minimization Pareto front, show at most ten representatives selected
  by lowest summed cost, and render an aligned text table.
- Optionally plot per-objective costs, combined cost, a Gaussian-smoothed combined
  trend, visible Pareto markers, optimization starts, and static-hash changes.

## I/O Format

- `build_rows(workspace, status="completed")` returns dictionaries containing row
  number, job name, normalized variables, dynamic costs, and available provenance.
- `view_cost(...)` returns `(summary_text, output_path_or_none)`.
- Relative plot paths resolve below `.yadof/tool_output/`; omitted plot paths mean
  summary-only operation, while `plot_rows(..., None)` creates a timestamped PNG.

## Non-Obvious Techniques

- Plot dependencies are imported lazily and matplotlib is forced to the headless
  `Agg` backend.
- Pareto membership uses strict all-objective minimization; the combined sum is for
  display/selection only and does not redefine dominance.
- Scatter size and opacity decrease for large histories, and the right combined
  axis is positioned so value one aligns meaningfully with the left cost axis.

## Mutability Profile

- Dynamic-cost reading and objective-width validation are framework contracts.
- Colors, markers, smoothing, and table presentation may evolve without changing
  recorded-data ownership or cost semantics.
