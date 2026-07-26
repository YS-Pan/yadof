# 2026-07-24 17:34 - Refine View Layout And Default Output

## Context

- Event lines had become more opaque than the original cost-view presentation.
- Separate legends occupied opposite corners instead of reading as one adjacent
  lower-left group.
- The compact plots needed more vertical space, a more prominent combined-cost
  average, and smaller scatter markers.
- Cost/time CLI users expected a timestamped image by default, matching the legacy
  `cost_YYYYMMDD_HHMMSS.png` behavior.

## Change

- Restored optimization-start and hash-change line opacity to `0.25`.
- Positioned the event legend immediately to the right of the measured data legend
  in the lower-left row, with both legend frames at `0.6` opacity.
- Changed both figures to 5.5 by 3.5 inches at the existing 600 dpi.
- Increased the smoothed combined-cost line from 2 to 4 points.
- Reduced ordinary scatter-marker diameter from 4 to 3 points and Pareto marker
  area from 40 to 30 square points.
- Made `yadof view cost` and `yadof view time` create timestamped PNGs by default,
  while retaining `--output` overrides and adding `--summary-only`.
- Updated CLI/agent/tool documentation and tests for filenames, default output,
  style alignment, image dimensions, and legend placement.

## Rationale

- The lower event opacity and translucent adjacent legends preserve data
  visibility while keeping provenance discoverable.
- A taller plot and heavier combined average improve readability without increasing
  width.
- Explicit `--summary-only` preserves a no-write CLI path while making the common
  image-producing workflow the default.

## Impact

- `yadof.cli`, `yadof.tools.view_cost`, `yadof.tools.view_time`, agent
  documentation, blueprints, and their tests changed.
- Python tool APIs still treat `output_path=None` as summary-only.
- Recorded evidence and cost/time calculations are unchanged.

## Follow-Up

- None.
