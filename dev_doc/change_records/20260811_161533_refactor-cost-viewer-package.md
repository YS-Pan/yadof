# 2026-08-11 16:15 - Refactor Cost Viewer Package

## Context

- Cost-history loading, analysis, text reporting, Matplotlib rendering, style
  constants, and orchestration had accumulated in one `tools/view_cost.py` file.
- A future unified `yadof.gui` needs a stable non-widget API rather than importing
  implementation details from a CLI-shaped monolith.
- The HV shade no longer needs explicit upper/lower line artists, and the CLI had
  redundant objective/progress text.

## Change

- Added `yadof.tools.cost_viewer` with separate API, history, analysis, report,
  plotting, style, and type modules plus a stable package export surface.
- Reduced `yadof.tools.view_cost` to a compatibility facade and changed the CLI to
  call the new package surface.
- Added a local cost-viewer developer-documentation tree describing its
  architecture, terminology, module contracts, and future GUI boundary.
- Removed HV boundary-line artists while keeping the shaded interval between the
  current-generation and cumulative-all-individual values.
- Removed the standalone `objectives:` summary line; objective names remain in the
  Pareto table header.
- Changed TTY progress completion to overwrite the active animation frame before
  ending the line, avoiding an extra repeated line.
- Updated root architecture, blueprints, terminology, user guidance, package
  artifact checks, and focused tests.

## Rationale

- The existing `surrogate_viewer` supplied the useful structural precedent:
  package-owned documentation, a stable package entry, backend/presentation
  separation, and optional dependency isolation. Its GUI/app/Torch structure was
  deliberately not copied because this change adds no GUI and cost history has a
  smaller numerical pipeline.
- The older `temp/20260811 from 2sc1970` branch remains useful for HV semantics,
  but its mixed GUI/file layout is not an appropriate integration boundary for the
  packaged project.
- Keeping CLI progress presentation outside `cost_viewer` lets a future GUI map the
  same callback to its own progress control without terminal coupling.

## Verification

- Build and force-install the wheel into the repository sibling `.venv`.
- Run focused cost-viewer, CLI, documentation, and artifact tests.
- Run the full package test suite from the installed wheel.
- Run `yadof view cost` against `20260807 saw` and inspect the generated PNG.

## Impact

- Existing `yadof.tools.view_cost` callers retain their import path.
- New CLI, Python, and future GUI integrations have a responsibility-focused
  `yadof.tools.cost_viewer` surface without widget dependencies.

## Follow-Up

- A unified GUI may be added later under `src/yadof/gui`; this change intentionally
  does not create it.
