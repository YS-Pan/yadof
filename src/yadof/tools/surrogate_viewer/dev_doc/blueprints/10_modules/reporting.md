# Module blueprint: terminal reporting

## Intent

Expose useful surrogate viewer metadata and cross-generation error results to
humans and AI agents without requiring a desktop window or image interpretation.

## Functionalities

- Build a schema-versioned workspace summary from the viewer backend without
  constructing a checkpoint predictor.
- Include checkpoint generation/sample/member counts, real-field-balanced policy,
  semantic state signature, completed-result counts, parameter ranges, objective
  names, and bounded rawData dimension spans. Do not present training-fit error as
  trust evidence.
- Resolve `all-costs`, `cost:NAME`, `all-rawdata`, and `rawdata:NAME` exactly
  against current task names before expensive inference.
- Run exactly one complete backend error audit for a valid audit command.
- Select relative, absolute, or both matrices from the completed aggregate without
  repeating inference.
- Render human-readable headings and tab-separated matrices or standard JSON.
- Convert missing/non-finite matrix cells to JSON `null`.

## I/O Format

Both payloads contain `schema_version`, `analysis`, and the resolved absolute
workspace. Summary payloads contain metadata lists. Audit payloads contain sample
fraction/seed, axis generations, per-row sample counts, resolved quantity, and one
or two matrices. Stdout contains only the final report; optional audit progress is
a separate stderr concern owned by CLI routing.

## Non-Obvious Techniques

- Dimension coordinate arrays are deliberately summarized as count/min/max so a
  large checkpoint grid cannot flood an agent context.
- JSON uses `allow_nan=False`; all array cells are normalized before encoding.
- Text is generated from the same payload as JSON so labels and axis order cannot
  drift.
- The reporting module imports the viewer backend only after CLI mode selection and
  never imports `app.py`, Tkinter, or Matplotlib.

## Mutability Profile

Presentation wording and additional backward-compatible payload fields may evolve.
Stable contracts are schema identification, row/column generation meaning, exact
quantity resolution, one inference pass for `both`, clean stdout, read-only
workspace behavior, and no GUI import.
