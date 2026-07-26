# File blueprint: src/yadof/tools/view_time.py

## Intent

- Summarize and visualize elapsed time from one workspace's recorded individual
  metadata. Failure-rate reporting belongs exclusively to `view_error.py`.

## Functionalities

- Read public record rows and optionally filter by canonical status; normalize the
  historical spelling `done` to `completed` and treat `all` as no filter.
- Parse ISO timestamps, including `Z` and timezone-aware values, into comparable
  local naive datetimes.
- Prefer explicit elapsed-minute/second metadata over timestamp subtraction and
  clamp negative durations to zero.
- Merge optimization metadata when individual records lack run/generation indices.
- Summarize time span, average elapsed time, completed-only average, and status
  counts.
- Optionally plot completed/failed evaluations, smoothed completed duration,
  optimization starts, generation bands, and static-input hash changes.
- Render cost-aligned 5.5-by-3.5-inch, 600-dpi figures with a compact font and line
  hierarchy, plus separate data and event legends.

## I/O Format

- `build_rows(workspace, status=None)` returns time-sorted dictionaries with job,
  status, start/end, elapsed minutes, success, and available provenance fields.
- `view_time(...)` returns `(summary_text, output_path_or_none)` without calculating
  or displaying failure rate.
- Relative PNG names resolve below `.yadof/tool_output/`. The Python API keeps an
  omitted plot path as summary-only, while the CLI defaults to
  `time_YYYYMMDD_HHMMSS.png` unless `--summary-only` is supplied.

## Non-Obvious Techniques

- Records lacking both usable start and end timestamps are skipped and counted for
  the empty-result diagnostic.
- Start/end fallback orders tolerate failed and partially recorded jobs, while
  explicit duration metadata avoids distorted elapsed time when lifecycle
  timestamps describe different stages.
- Matplotlib/numpy imports are lazy and use the headless `Agg` backend.
- Completed-evaluation circles use the shared 0.4-point ordinary-marker edge so
  their rings remain lighter than emphasized viewCost points.
- The orange average-time line uses the shared average-trend opacity of 0.25,
  matching viewCost's translucent average-cost trend.
- Contiguous generations are scoped by optimization run, labeled with their
  zero-based generation index inside the plot, and odd generations use a black
  background at 10% opacity.
- Optimization-start and hash-change lines use equal-length complementary dash
  phases, butt caps, and opacity 0.25, so coincident event lines remain independently
  visible without dominating the data.
- The translucent data and event legends share the lower-left row; the event
  legend is positioned immediately to the right of the measured data legend, and
  both are inset from the axes frame by 0.015 axes units.
- Shared dimensions, typography, widths, generation styling, event dashes, and
  event names mirror `view_cost.py` under the tools module alignment contract.

## Mutability Profile

- Timestamp/status normalization and workspace-explicit reads are stable contracts.
- Plot styling and smoothing windows may change independently of record schemas.
