# 2026-07-24 17:55 - Refine Legends And Pareto Emphasis

## Context

- The lower-left legends sat directly against the axes frame.
- Pareto marker rings were visually heavy, while the emphasized cost points did
  not stand out enough from ordinary samples.

## Change

- Inset both data and event legends by `0.015` axes units from the lower and left
  plot edges while retaining their adjacent layout.
- Increased viewCost Pareto marker area from 30 to 60 square points.
- Reduced viewCost Pareto ring width from 1.0 to 0.5 points.
- Updated the cost/time alignment blueprint, file blueprints, and style tests.

## Rationale

- A small axes-relative inset gives both legends breathing room at every output
  size.
- Larger marker faces and thinner rings strengthen point emphasis without making
  the outline dominate the data.

## Impact

- `yadof.tools.view_cost`, `yadof.tools.view_time`, plot documentation, and their
  tests changed.
- Plot dimensions, calculations, recorded evidence, CLI behavior, and output
  naming are unchanged.

## Follow-Up

- None.
