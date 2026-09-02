# 2026-07-24 16:06 - Label And Shade Cost Generations

## Context

- Cost plots showed optimization starts but did not make individual generation
  ranges visible.
- Users needed zero-based generation numbers and alternating generation backgrounds
  to read long optimization histories more easily.

## Change

- Grouped contiguous cost-plot rows by optimization run and generation metadata.
- Added each generation index inside the top of its plot region.
- Added a light-gray background with 10% opacity to odd-numbered generations.
- Kept rows without generation metadata outside generation bands.
- Added focused tests for run boundaries, missing generation metadata, labels, and
  odd-generation styling.

## Rationale

- Run-aware grouping handles histories in which every optimization run restarts at
  generation zero.
- Alternating only odd generations preserves a white background for even
  generations while making adjacent ranges distinguishable without obscuring cost
  points.

## Impact

- `yadof.tools.view_cost` PNG presentation and its file blueprint changed.
- Recorded evidence, dynamic cost calculation, text summaries, and CLI/API shapes
  are unchanged.

## Follow-Up

- None.
