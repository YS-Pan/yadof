# File blueprint: src/yadof/tools/view_time.py

## Intent

- Summarize and visualize elapsed time, execute-machine distribution, failure rate,
  and typed error occurrences from one workspace's recorded individual metadata.

## Functionalities

- Read public record rows and optionally filter by canonical status; normalize the
  historical spelling `done` to `completed` and treat `all` as no filter.
- Parse ISO timestamps, including `Z` and timezone-aware values, into comparable
  local naive datetimes.
- Prefer explicit elapsed-minute/second metadata, including Condor execution-clock
  duration, over timestamp subtraction and clamp negative durations to zero.
- Resolve timing fields across both the individual record and nested job metadata.
  Prefer workflow or execute start time; use batch `recorded_at` only as a last
  resort so failed rows are not clustered at generation publication boundaries.
- Merge optimization metadata when individual records lack run/generation indices.
- Prefer execute-machine identity from worker-support-written individual metadata;
  fall back to source-labeled `condor_execute_machine` for timed-out jobs whose
  worker file did not return. Normalize older remote-host spellings only as
  compatibility reads and never let a scheduler value override worker identity.
- For historical timeout records without the new field, derive an in-memory
  fallback from recorded `condor_log_tail`. Assign the machine for an active
  removal/hold, an eviction explicitly caused by `condor_rm`, or a terminal segment
  not collected before the central deadline. A normally evicted or never-executed
  queued job stays `unknown`.
- Classify failures by explicit error type, then timeout, failure stage, or status.
- Summarize time span, average elapsed time, completed-only average, failure rate,
  status/type counts, and each error occurrence.
- Color ordinary elapsed-time points by execute machine and plot a smoothed
  completed duration.
- Label each machine in the legend as `<machine> (avg. <minutes> min)`, where the
  mean uses completed rows assigned to that machine. Keep failure-only machines in
  the color legend as `<machine> (avg. n/a)` without treating failure duration as
  zero or as a completed runtime.
- Place each error type on its own axes-relative horizontal band between 80% and 90%
  of plot height. Draw each error point with machine-colored fill and an
  error-type-colored outer ring.
- Label error bands directly inside the left side of the plot rather than adding
  error types to a centralized legend; vertically center each label on its band.
- Plot highly transparent smoothed failure percentage on a secondary right axis,
  plus optimization starts, generation bands, and static-input hash changes.
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
- Start/end fallback orders span top-level records and nested job metadata, tolerate
  failed and partially recorded jobs, and keep execution starts ahead of batch
  publication timestamps. Explicit duration metadata avoids distorted elapsed time
  when lifecycle timestamps describe different stages.
- Matplotlib/numpy imports are lazy and use the headless `Agg` backend.
- Completed-evaluation circles use the shared 0.4-point ordinary-marker edge and
  their fill color identifies the execute machine.
- Machine lookup is provenance-ordered by key rather than record nesting:
  `execute_machine`, then `condor_execute_machine`, then legacy remote-host fields.
  Thus a nested worker value still wins over a top-level scheduler fallback.
- Stored log-tail fallback runs only for timeout/timed-out rows and never opens a
  job directory or mutates recorded metadata.
- Error bands use `ax.get_xaxis_transform()` so their 0.80–0.90 heights stay near
  the visual top regardless of elapsed-time units. The elapsed-time y-limit keeps
  ordinary data at or below 72% of axes height to reserve that error region. Error
  labels use `ax.transAxes`, left alignment, and vertical centering on the line so
  names extend inward from the left edge without sitting above the band.
- Error markers use one Matplotlib circle with machine facecolor and error-type
  edgecolor, preserving both encodings without a separate error legend.
- Machine and error palettes are deterministic and assign distinct colors within
  each category set.
- The orange average-time line uses the shared average-trend opacity of 0.25,
  matching viewCost's translucent average-cost trend.
- The dark-blue failure-rate line remains plot-specific and uses alpha 0.1 so it
  stays visible without dominating the time data or error bands.
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
