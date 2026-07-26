# 2026-07-24 18:35 - Align Emphasis And Time Trend Opacity

## Context

- Emphasized combined-cost points had a thinner ring than emphasized individual
  costs.
- The average-time line was fully opaque while the reference average-cost trend
  was translucent.

## Change

- Restored the 0.75-point Pareto ring for emphasized combined-cost points, matching
  emphasized individual-cost points. Ordinary combined-cost circles remain at
  0.4 points.
- Added the shared `TREND_LINE_ALPHA = 0.25` constant to viewTime and applied it to
  the orange average-time line.
- Updated plot alignment documentation, file blueprints, and tests.

## Rationale

- Emphasis styling should not change between the individual and combined axes.
- Matching average-trend opacity keeps viewTime aligned with viewCost and prevents
  the orange curve from dominating the timing samples.

## Impact

- `yadof.tools.view_cost`, `yadof.tools.view_time`, plot documentation, and their
  tests changed.
- Marker sizes, trend widths, calculations, recorded evidence, and CLI behavior
  are unchanged.

## Follow-Up

- None.
