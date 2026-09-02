# 2026-08-15 20:03 - Draw Hypervolume Boundaries

## Context

- The cost view rendered the interval between cumulative and current-generation
  hypervolume as a stepped, shade-only band. Its values were difficult to follow
  precisely in denser plots.

## Change

- Replaced the stepped HV fill with a shaded band that follows the generation
  plotting positions.
- Added thin, translucent upper and lower polylines for cumulative and
  current-generation HV.
- Updated the viewer, project, and user-facing visual contracts and regression
  coverage.

## Rationale

- The two boundaries make the two HV series legible while preserving the visual
  context of their difference. Thin transparent lines avoid competing with the
  deliberately heavier average-cost trend.

## Impact

- `yadof view cost` and Python callers render the same HV values and legend, with
  a clearer continuous interval shape.

