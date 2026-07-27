# 2026-07-27 15:19 - Integrate Surrogate Viewer

## Context

- The surrogate checkpoint viewer had been developed as a nested standalone
  package beside yadof.
- Users needed the current viewer implementation, GUI, backend, tests, and
  developer documentation to ship as an official yadof tool without weakening its
  read-only workspace boundary.

## Change

- Added the viewer as `src/yadof/tools/surrogate_viewer/`, preserving its
  `backend/`, `ui/`, and relatively independent `dev_doc/` structure.
- Added the lazy `yadof view surrogate [--workspace PATH]` CLI route and the
  equivalent nested module entry.
- Added the `viewer` optional dependency group for Torch and Matplotlib while
  keeping CLI construction and the viewer package root lightweight.
- Moved maintained viewer tests into the package's top-level `tests/` contract and
  added CLI, documentation-link, optional-dependency, and wheel/sdist membership
  coverage.
- Updated root agent/developer documentation, architecture, blueprints,
  terminology, and package usage guidance; the root developer README now links to
  the viewer's own documentation entry.

## Rationale

- Keeping the viewer below `yadof.tools` makes it a clear optional leaf rather than
  a core evaluation dependency.
- Lazy imports preserve core-only help, documentation, and non-GUI tools.
- Retaining a nested developer-documentation tree preserves the viewer's detailed
  UI, concurrency, checkpoint, and audit contracts without duplicating them across
  yadof's root documentation.

## Impact

- Wheel and sdist artifacts now contain the viewer source and its developer docs.
- Users install `yadof[viewer]` and launch the GUI explicitly with
  `yadof view surrogate`.
- The viewer remains read-only: it does not train models, execute workflows,
  publish audits, or modify configuration, recorded evidence, or checkpoints.

## Follow-Up

- Package-internal checkpoint/model/rawData calls remain isolated in the viewer
  backend. They can move behind broader public surrogate APIs later if a non-yadof
  consumer needs the same contracts.
