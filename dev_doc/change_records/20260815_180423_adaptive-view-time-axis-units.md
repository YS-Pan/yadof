# 2026-08-15 18:04 - Adapt View Time Axis Units

## Context

`yadof view time` always imposed a one-minute lower bound on its elapsed-time
axis. Fast evaluations that complete in seconds or milliseconds therefore appeared
compressed against the horizontal axis.

## Change

- Select minutes, seconds, or milliseconds automatically from the maximum completed
  elapsed duration.
- Scale completed markers and average-time legend/trend values into the selected
  unit, and use a data-proportional upper limit with a bounded linear tick locator.
- Add regression coverage for unit selection and a five-millisecond rendered fast
  evaluation.
- Document the automatic units in the user workflow and tool blueprints.

## Rationale

Keeping the existing axes-relative error bands while removing the fixed one-minute
floor preserves the visual layout and makes fast evaluations readable without a
new user option.

## Impact

`yadof view time` and `yadof view all` automatically render minute-, second-, and
millisecond-scale completed timing data with matching average-time labels. The
record format, summaries, CLI arguments, and error/failure encodings are unchanged.

## Follow-Up

No follow-up is required. Durations below one millisecond remain represented as
fractional milliseconds.
