# 2026-07-30 16:38 - Add Selectable Surrogate Viewer Dimensions

## Context

- Surrogate rawData may contain scalar through three-dimensional arrays and may
  gain higher-rank data later, while the viewer previously chose one fixed
  one-dimensional slice automatically.
- Users needed to choose the plotted dimensions and control every remaining slice
  coordinate.

## Change

- Added viewer-local dimension and plot-slice contracts that describe all rawData
  axes and extract user-selected zero-, one-, or two-dimensional views from
  arbitrary-rank data.
- Added one dimension row per rawData axis. Users can select at most two plot axes;
  fixed inputs snap to the nearest stored coordinate.
- Added scalar number, curve, and filled two-dimensional color-contour rendering.
  Two-dimensional real and surrogate results use a shared scale in adjacent plots.
- Reused one finite ensemble-bounds reduction for the retained curve API and the
  new generic plot path.
- Extended focused tests and current root/viewer documentation.

## Rationale

- Keeping slicing in the backend gives predicted, ensemble-member, and real data
  identical coordinate semantics while the UI remains responsible only for user
  intent and presentation.
- Nearest-coordinate selection avoids interpolation assumptions and always
  displays values that exist in the stored rawData grid.

## Impact

- The optional read-only surrogate viewer gains dimension selection without
  changing checkpoint inference, workspace persistence, optimization, or audit
  aggregation.
- The previous frequency-first one-dimensional view remains the default when a
  `Freq` axis exists.

## Follow-Up

- Two-dimensional plots intentionally show the ensemble mean and optional real
  surface; a future uncertainty-surface design would need a separate visual
  contract.
