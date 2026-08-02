# File blueprint: src/yadof/tools/view_cost.py

## Intent

- Turn one workspace's recorded raw evidence into a current-cost text summary and
  optional static PNG without persisting cost as authoritative history.

## Functionalities

- Read historical results through `recorded_data.api.get_historical_results()` so
  costs are recalculated by the current task.
- Merge individual and optimization metadata to annotate optimization starts,
  generation/run identity, and static-input hash changes.
- Validate finite numeric variables/costs, finite combined sums, and one consistent
  objective width; isolate unusable rows and report bounded details instead of
  aborting when valid rows remain.
- Treat individual/optimization metadata as optional plot annotations and fall back
  to generic objective labels when task names cannot be read.
- Obtain task objective names when their count matches, with deterministic generic
  fallbacks.
- Identify the minimization Pareto front, show at most ten representatives selected
  by lowest summed cost, and render an aligned text table.
- Optionally plot per-objective costs, combined cost, a Gaussian-smoothed combined
  trend, visible Pareto markers, optimization starts, generation bands, and
  static-hash changes.
- Render cost/time-aligned 5.5-by-3.5-inch, 600-dpi figures with a compact font and
  line hierarchy, plus separate data and event legends.
- Scale and explicitly place right-axis ticks so, for `N` objectives, combined cost
  `N` aligns with individual cost `1` and every visible left/right tick is aligned.

## I/O Format

- `build_rows(workspace, status="completed")` returns dictionaries containing row
  number, job name, normalized variables, dynamic costs, finite combined cost, and
  available provenance. Its optional issue collector receives skipped-row and
  ignored-annotation diagnostics.
- `view_cost(...)` returns `(summary_text, output_path_or_none)`.
- Relative plot paths resolve below `.yadof/tool_output/`. The Python API keeps an
  omitted plot path as summary-only, while the CLI defaults to
  `cost_YYYYMMDD_HHMMSS.png` unless `--summary-only` is supplied.

## Non-Obvious Techniques

- Plot dependencies are imported lazily and matplotlib is forced to the headless
  `Agg` backend.
- Pareto membership uses strict all-objective minimization; the combined sum is for
  display/selection only and does not redefine dominance.
- When historical objective widths disagree, the most common finite width is used
  so a stray row cannot select or block the plot; original row numbers remain the
  evaluation-index axis after filtering.
- Scatter size and opacity decrease for large histories, and the right combined
  axis is an exact objective-count multiple of the left individual-cost axis.
- The smoothed average combined-cost line is deliberately thicker than ordinary
  time/cost trends so it remains visually prominent.
- Individual-cost Pareto points use a larger 60-square-point marker with a
  0.75-point ring, making selected points prominent without a heavy outline.
  Emphasized combined-cost points use the same ring width, while ordinary
  combined-cost circles use a lighter 0.4-point edge.
- Contiguous generations are scoped by optimization run, labeled with their
  zero-based generation index inside the top of the plot, and odd generations use
  a black background at 10% opacity. Rows without generation metadata are not
  assigned a generation band.
- Optimization-start and hash-change lines use equal-length complementary dash
  phases, butt caps, and the original viewCost opacity of 0.25, so coincident event
  lines remain independently visible without dominating the data.
- The translucent data and event legends share the lower-left row; the event
  legend is positioned immediately to the right of the measured data legend, and
  both are inset from the axes frame by 0.015 axes units.
- Shared dimensions, typography, widths, generation styling, event dashes, and
  event names follow the cost/time alignment contract in the tools module
  blueprint; this file is the reference when no request says otherwise.

## Mutability Profile

- Dynamic-cost reading, row-level display isolation, issue reporting, and
  objective-width validation are framework contracts.
- Colors, markers, smoothing, and table presentation may evolve without changing
  recorded-data ownership or cost semantics.
