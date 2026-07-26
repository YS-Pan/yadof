# 2026-07-24 17:06 - Align Cost And Time Plots

## Context

- Cost and time PNGs used different dimensions, font sizes, line widths, event
  names, and event-line styles.
- Only the cost plot showed generation ranges.
- Coincident optimization-start and static-hash-change lines could obscure each
  other.
- The cost plot's individual and combined axes did not provide a complete
  objective-count-scaled tick alignment.

## Change

- Standardized both figures at 5.5 by 3 inches and 600 dpi, with 10-point medium
  text and shared title, tick, legend, generation, width, and marker hierarchies.
- Added optimization-run-aware generation labels and odd-generation background
  bands to the time plot.
- Changed odd-generation bands in both plots to black at 10% opacity.
- Renamed event labels to `Opt. start` and `Hash change`, and moved them into a
  separate event legend.
- Made optimization-start and hash-change lines use complementary `(4, 4)` dash
  phases, equal widths, and butt dash caps.
- Scaled the cost plot's combined axis by the objective count and explicitly
  aligned its ticks with the individual-cost ticks.
- Documented `view_cost.py` as the default visual reference for shared cost/time
  styling and added cross-view alignment tests.

## Rationale

- A compact shared style produces directly comparable figures and prevents
  independent visual drift.
- Complementary dash phases keep coincident event lines visible without changing
  their event locations.
- Objective-count scaling makes combined cost `N` occupy the same position as
  individual cost `1` for `N` objectives and aligns all displayed tick positions.

## Impact

- `yadof.tools.view_cost`, `yadof.tools.view_time`, their tests, and tools
  blueprints changed.
- Recorded evidence, summaries, task contracts, and CLI/API return shapes are
  unchanged.

## Follow-Up

- None.
