# 2026-07-27 16:33 - Reduce Failure-Rate Line Opacity

## Context

- The preceding time-view change interpreted a request for greater transparency as
  a request for greater opacity and raised the failure-rate line alpha to 1.0.
- The intended result is a substantially more transparent failure-rate line.

## Change

- Reduced the plot-specific failure-rate line alpha from 1.0 to 0.1.
- Updated the focused plot assertions and current tools blueprints.

## Rationale

- Alpha 0.1 makes the failure-rate trend contextual rather than visually dominant
  while preserving its data, color, line width, legend entry, and secondary axis.

## Impact

- Only failure-rate line presentation and its current documentation/tests changed.
- Timing calculations, summaries, recorded metadata, and other plot elements are
  unchanged.

## Follow-Up

- None.
