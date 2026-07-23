# File blueprint: src/yadof/tools/view_time.py

## Intent

- Summarize and visualize elapsed time and failure rate from one workspace's
  recorded individual metadata.

## Functionalities

- Read public record rows and optionally filter by canonical status; normalize the
  historical spelling `done` to `completed` and treat `all` as no filter.
- Parse ISO timestamps, including `Z` and timezone-aware values, into comparable
  local naive datetimes.
- Prefer explicit elapsed-minute/second metadata over timestamp subtraction and
  clamp negative durations to zero.
- Merge optimization metadata when individual records lack run/generation indices.
- Summarize time span, average elapsed time, completed-only average, failure rate,
  and status counts.
- Optionally plot completed/failed evaluations, smoothed completed duration,
  smoothed failure percentage, optimization starts, and static-input hash changes.

## I/O Format

- `build_rows(workspace, status=None)` returns time-sorted dictionaries with job,
  status, start/end, elapsed minutes, success, and available provenance fields.
- `view_time(...)` returns `(summary_text, output_path_or_none)`.
- Relative PNG names resolve below `.yadof/tool_output/`; rendering dependencies are
  not required for text-only summaries.

## Non-Obvious Techniques

- Records lacking both usable start and end timestamps are skipped and counted for
  the empty-result diagnostic.
- Start/end fallback orders tolerate failed and partially recorded jobs, while
  explicit duration metadata avoids distorted elapsed time when lifecycle
  timestamps describe different stages.
- Matplotlib/numpy imports are lazy and use the headless `Agg` backend.

## Mutability Profile

- Timestamp/status normalization and workspace-explicit reads are stable contracts.
- Plot styling and smoothing windows may change independently of record schemas.
