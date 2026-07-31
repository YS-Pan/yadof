# 2026-07-30 17:33 - Clarify Surrogate Viewer Toggles

## Context

- The active ttk theme rendered selected checkboxes with an X, which looked like a
  rejection or error state rather than selection.
- The long automatic-prediction label occupied unnecessary space.

## Change

- Added one shared keyboard-operable checkmark toggle that renders an empty square
  while inactive and a white checkmark on an accent-filled control while active.
- Applied it to rawData plot-dimension selection and renamed the automatic
  prediction control to `Auto refresh`.
- Documented the distinction between arbitrary continuous task-parameter queries
  and fixed-grid rawData slice coordinates.

## Rationale

- Rendering the state explicitly avoids platform/theme-dependent indicator glyphs
  while retaining BooleanVar state, focus, click, and Space-key behavior.
- `Auto refresh` describes the user-visible effect concisely; it does not imply
  model training or background workspace polling.

## Impact

- Viewer selection state is visually unambiguous and uses less horizontal space.
- Surrogate inference, checkpoint schemas, workspace persistence, and audit
  behavior are unchanged.

## Follow-Up

- Off-grid rawData-coordinate inference remains outside the current checkpoint
  reconstruction contract; viewer-only interpolation could be considered
  separately if its meaning is made explicit.
