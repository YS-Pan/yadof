# 2026-09-02 12:28 - Add Headless Surrogate Case Inspection

## Context

- The integrated viewer already exposed bounded workspace summaries and
  cross-generation audits to AI agents, but reproducing one GUI checkpoint versus
  one recorded individual still required a desktop window or bespoke code.
- Agent diagnosis needs exact selectors, bounded standard JSON, explicit truth
  absence for off-grid output, and portable evidence that is separate from
  immutable workspace records/checkpoints.

## Change

- Added `yadof view surrogate inspect` with exact checkpoint, job or
  generation/population, rawData, plot-dimension, and fixed-coordinate selection.
- Added a viewer-local inspection use case that reuses `SurrogateWorkspace.predict_one`,
  extracts stored-grid or off-grid 0D/1D/2D plots, aligns current objectives, and
  reports finite prediction/truth/member/error statistics. JSON inlines at most
  4096 selected scalars and maps every non-finite value to `null`.
- Added optional collision-free evidence export containing selected arrays in NPZ,
  a pure Figure/Agg PNG, one-dimensional CSV where applicable, and a last-published
  manifest with relative paths, sizes, and SHA-256 digests.
- Added typed stable runtime errors shared by terminal summary/audit/inspect. After
  argparse succeeds, JSON failures produce no stdout and exactly one error object
  on stderr.
- Preserved the bare GUI, summary/audit success schemas, one-pass audit semantics,
  and read-only workspace boundary.

## Rationale

- Keeping selection/statistics/export in a separate use-case module prevents CLI
  routing and the GUI from acquiring a second inference implementation.
- A dedicated Agg-only renderer makes the no-window boundary reviewable and
  testable; it has no Tk, pyplot, workspace, or model responsibility.
- Bounded stdout is suitable for agent context, while explicit NPZ/PNG/CSV export
  retains full selected evidence when deeper analysis is needed.
- Publishing the manifest after exclusive artifact publication prevents failed or
  colliding output from appearing complete.

## Impact

- Users and agents can reproduce one saved surrogate diagnosis deterministically
  in text or JSON and may request a self-contained evidence directory.
- `summary` and `audit` remain zero-write. `inspect` is also zero-write unless
  `--output` is supplied, and it never changes config, history, recorded data, or
  checkpoints.
- The wheel/sdist now include the inspection, renderer, error, and synchronized
  viewer/root documentation contracts; the source suite includes their tests.

## Follow-Up

- None.
