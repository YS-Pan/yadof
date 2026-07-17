# 2026-07-18 07:08 - Fix ViewTime Bootstrap And Enlarge ViewCost Text

## Context

Running `project/tools/viewTime.py` directly with a lightweight Python interpreter
first failed to locate the `project` package and then imported NumPy-dependent cost
code before timing records were read. The cost plot text was also too small for the
current output size.

## Change

- Added a source-tree package bootstrap for direct tool launches that registers the
  `project` package without adding the repository root to `sys.path`.
- Changed `viewTime.py` to read individual and optimization timing metadata through
  the lightweight recorded-data manifest helpers.
- Made manifest reads standard-library-only by loading NumPy-aware JSON conversion
  only inside manifest write operations.
- When the invoking interpreter lacks NumPy or matplotlib, `viewTime.py` re-runs
  through the existing `HTCONDOR_PYTHON_EXE` interpreter when it is available.
- Increased `viewCost.py`'s default plot font from 12 to 14 points and its explicit
  legend font from 10 to 12 points.
- Added focused tests for dependency-light timing imports, path handling, and font
  sizes.

## Rationale

Timing summaries do not calculate costs or load rawData, so they should not acquire
the cost stack's NumPy dependency. Direct tools still need a package context, but
that context can be registered explicitly without mutating the import search path.

## Impact

Direct `viewTime.py` launches work from outside the repository package context and
can use the configured yadof plotting environment automatically. Cost PNGs render
all default text two points larger.

## Follow-Up

None.
