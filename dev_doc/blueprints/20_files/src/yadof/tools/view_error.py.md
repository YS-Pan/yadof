# File blueprint: src/yadof/tools/view_error.py

## Intent

- Own failure-rate reporting and expose when each failed evaluation occurred,
  without mixing failure diagnostics into elapsed-time visualization.

## Functionalities

- Read every public recorded individual row and normalize `done` to `completed`.
- Choose each evaluation's most useful terminal/event time from failure, end,
  runner-finish, record, and start timestamps.
- Treat every non-completed status as a failure for the same denominator formerly
  used by viewTime.
- Prefer explicit `error_type`/`failure_type`, then fall back to timeout,
  failure-stage, or status classifications.
- Summarize total rows, failure count/rate, type counts, and every error occurrence
  with time, type, job, and available message.
- Plot error occurrence time on the x-axis and categorical error type on the
  y-axis, using a deterministic distinct color for each type.
- Plot smoothed failure percentage on a secondary 0–100% axis and support a valid
  zero-error history.

## I/O Format

- `build_rows(workspace)` returns time-sorted dictionaries containing job, status,
  event time, failure flag, error type, and message.
- `view_error(...)` returns `(summary_text, output_path_or_none)`.
- Relative PNG names resolve below `.yadof/tool_output/`. The Python API keeps an
  omitted plot path as summary-only behavior, while the CLI defaults to
  `error_YYYYMMDD_HHMMSS.png` unless `--summary-only` is supplied.

## Non-Obvious Techniques

- Failure rate is calculated across all usable evaluation rows; filtering only
  failures would make the rate meaningless.
- A categorical time scatter preserves every occurrence and makes repeated or
  clustered error types visible while color supplies a second type encoding.
- HSV colors are generated from the first-occurrence type order, guaranteeing
  different colors without imposing a fixed maximum number of types.
- Matplotlib/numpy imports are lazy and use the headless `Agg` backend.

## Mutability Profile

- Failure ownership, denominator semantics, occurrence-time preservation, and
  explicit-type precedence are stable contracts.
- Colors, markers, smoothing, and table layout may evolve without changing
  recorded-data semantics.
