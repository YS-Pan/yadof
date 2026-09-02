# 2026-07-24 18:24 - Balance Scatter Ring Widths

## Context

- The reduced Pareto ring was too faint after the previous refinement.
- Ordinary combined-cost and completed-time circles retained Matplotlib's heavier
  default marker edge.

## Change

- Increased the viewCost Pareto ring width from 0.5 to 0.75 points.
- Added a shared 0.4-point scatter edge and applied it to all combined-cost circles,
  including emphasized points, and completed-evaluation circles in viewTime.
- Updated alignment documentation, file blueprints, and style tests.

## Rationale

- The two widths create a visible hierarchy: individual-cost Pareto emphasis
  remains crisp while combined-cost and viewTime circular markers keep a lighter
  ring.

## Impact

- `yadof.tools.view_cost`, `yadof.tools.view_time`, plot documentation, and their
  tests changed.
- Marker sizes, plot calculations, recorded evidence, and CLI behavior are
  unchanged.

## Follow-Up

- None.
