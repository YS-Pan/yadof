# 2026-07-22 10:57 - Document Tools And Parse Inline HFSS Parameters

## Context

- `src/yadof/tools/` had a module blueprint but no mirrored file-level blueprints.
- Current AEDT projects can store optimization attributes directly inside
  `VariableProp(..., oa(...))`; the direct parser recognized only standalone
  Optimetrics variable records and would unnecessarily fall back to PyAEDT.
- A continuous variable's AEDT `Level` envelope can differ from its configured
  `Min`/`Max` bounds.

## Change

- Added file-level blueprints for every Python file under `src/yadof/tools/`,
  including the HFSS subpackage.
- Added direct parsing for inline optimization attributes and made continuous
  ranges use `Min`/`Max` while retaining discrete `Level` value lists.
- Moved the command to `yadof task hfss extract-parameters`, giving
  software-specific task tools an explicit namespace for future expansion.
- Expanded agent extraction guidance and focused parser/CLI regression tests.
- Replaced a stale pre-package source-path comment with a current module docstring.

## Rationale

- Complete file blueprints make each optional tool reconstructible without
  weakening the module-level package/workspace boundary.
- Direct parsing avoids an unnecessary AEDT launch and writes the optimization
  bounds users configured rather than a wider continuous level envelope.

## Impact

- `yadof task hfss extract-parameters` handles both supported textual AEDT variable
  encodings before PyAEDT fallback; no ambiguous generic extraction alias remains.
- Existing confirmation, backup, AST-only `PARAMETERS` replacement, and atomic
  publication behavior remain unchanged.

## Follow-Up

- Additional current AEDT encodings should be added only with representative
  parser fixtures and CLI coverage.
