# File blueprint: src/yadof/tools/view_time.py

## Intent

- Summarize and visualize elapsed time, execute-machine distribution, failure rate,
  and typed error occurrences from one workspace's recorded individual metadata.

## Functionalities

- Read public record rows and optionally filter by canonical status; normalize the
  historical spelling `done` to `completed` and treat `all` as no filter.
- Parse ISO timestamps, including `Z` and timezone-aware values, into comparable
  local naive datetimes.
- Prefer explicit elapsed-minute/second metadata over timestamp subtraction and
  clamp negative durations to zero.
- Merge optimization metadata when individual records lack run/generation indices.
- Read execute-machine identity from workflow-written individual metadata; normalize
  old remote-host spellings only as a compatibility read and never query the submit
  host for the machine.
- Classify failures by explicit error type, then timeout, failure stage, or status.
- Summarize time span, average elapsed time, completed-only average, failure rate,
  status/type counts, and each error occurrence.
- Color ordinary elapsed-time points by execute machine and plot a smoothed
  completed duration.
- Place each error type on its own axes-relative horizontal band between 80% and 90%
  of plot height. Draw each error point with machine-colored fill and an
  error-type-colored outer ring.
- Label error bands directly inside the right side of the plot rather than adding
  error types to a centralized legend.
- Plot smoothed failure percentage on a secondary right axis, plus optimization
  starts, generation bands, and static-input hash changes.
- Render cost-aligned 5.5-by-3.5-inch, 600-dpi figures with a compact font and line
  hierarchy, plus separate data and event legends.

## I/O Format

- `build_rows(workspace, status=None)` returns time-sorted dictionaries with job,
  status, start/end/event times, elapsed minutes, success/failure, computer, error
  classification/message, and available provenance fields.
- `view_time(...)` returns `(summary_text, output_path_or_none)`.
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
- Completed-evaluation circles use the shared 0.4-point ordinary-marker edge and
  their fill color identifies the execute machine.
- Error bands use `ax.get_xaxis_transform()` so their 0.80–0.90 heights stay near
  the visual top regardless of elapsed-time units. The elapsed-time y-limit keeps
  ordinary data at or below 72% of axes height to reserve that error region. Error
  labels use `ax.transAxes` and right alignment so long names extend inward instead
  of outside the axes.
- Error markers use one Matplotlib circle with machine facecolor and error-type
  edgecolor, preserving both encodings without a separate error legend.
- Machine and error palettes are deterministic and assign distinct colors within
  each category set.
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

- Timestamp/status normalization, execute-side machine provenance, failure-rate
  ownership, and workspace-explicit reads are stable contracts.
- Plot styling and smoothing windows may change independently of record schemas.
