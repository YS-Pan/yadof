# 2026-07-31 14:51 - Add Surrogate Text Reports

## Context

- The integrated surrogate viewer exposed useful checkpoint metadata and
  cross-generation error analysis only through a desktop GUI.
- AI coding agents needed a stable way to inspect the same results as text instead
  of interpreting screenshots or automating Tkinter.

## Change

- Preserved bare `yadof view surrogate` as the GUI and added explicit `gui`,
  `summary`, and `audit` modes.
- Added a viewer-local terminal reporter. `summary` emits bounded
  checkpoint/history/task/rawData metadata without model inference. `audit` reuses
  the existing complete backend audit and emits selected cost/rawData
  relative/absolute matrices.
- Added human-readable and schema-versioned JSON encodings, deterministic
  per-generation sampling, exact named-quantity selection, standard JSON `null`
  values for missing finite cells, and optional stderr-only progress.
- Updated user guidance, root/viewer architecture, blueprints, terminology,
  artifact assertions, parser coverage, and focused report tests.

## Rationale

- Reusing `SurrogateWorkspace` and `CrossGenerationErrorAudit` keeps GUI and CLI
  analysis mathematically identical and avoids a second checkpoint interpretation
  path.
- Bounded metadata and JSON make the output suitable for AI context windows and
  programmatic parsing. Clean stdout allows direct capture while long-running
  inference can still report progress.
- The report remains a viewer leaf: core CLI construction stays lightweight,
  Tkinter/Matplotlib are not loaded by terminal modes, and no workspace cache or
  plot is created.

## Impact

- Users and agents can run `yadof view surrogate summary|audit` against an explicit
  workspace or the current directory.
- Existing GUI invocations remain compatible.
- The `viewer` extra is still required because terminal reports use the same
  Torch-backed viewer backend; Tkinter is required only for the GUI.

## Follow-Up

- None.
