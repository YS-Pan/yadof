# Module blueprint: terminal reporting

## Intent

Expose useful surrogate viewer metadata, cross-generation error results, and one
deterministic real-case diagnosis to humans and AI agents without requiring a
desktop window or image interpretation.

## Functionalities

- Build a schema-versioned workspace summary from the viewer backend without
  constructing a checkpoint predictor.
- Include active strategy/run/component identity, checkpoint
  generation/sample/member counts, real-field-balanced policy, semantic state
  signature, completed-result counts, parameter ranges, objective names, and
  bounded rawData dimension spans. Do not present training-fit error as trust
  evidence.
- Resolve `all-costs`, `cost:NAME`, `all-rawdata`, and `rawdata:NAME` exactly
  against current task names before expensive inference.
- Run exactly one complete backend error audit for a valid audit command.
- Select relative, absolute, or both matrices from the completed aggregate without
  repeating inference.
- Render human-readable headings and tab-separated matrices or standard JSON.
- Convert missing/non-finite matrix cells to JSON `null`.
- Resolve one exact checkpoint, completed real result, rawData name, zero to two
  plot dimensions, and every fixed coordinate before one backend prediction.
- Preserve stored-grid truth/error and explicitly omit both for off-grid output.
- Inline no more than 4096 selected plot scalars; retain shape/finite statistics
  and an export hint above that bound.
- On explicit output only, write full NPZ arrays, one-dimensional CSV, and a pure
  Agg diagnostic PNG, then publish a hashed manifest last without replacement.
- Normalize parsed-command runtime failures to stable text or one-object standard
  JSON stderr while leaving failed JSON stdout empty.

## I/O Format

Both payloads contain `schema_version`, `analysis`, the resolved absolute
workspace, and strategy/run/component scope. Summary payloads contain metadata
lists. Audit payloads contain sample
fraction/seed, axis generations, per-row sample counts, resolved quantity, and one
or two matrices. Inspection payloads add exact checkpoint/result/parameter/query
identity, bounded prediction/truth/ensemble arrays, aligned objectives, error
statistics, warnings, and artifacts. Stdout contains only the final report;
optional audit progress is a separate stderr concern owned by CLI routing.

## Non-Obvious Techniques

- Dimension coordinate arrays are deliberately summarized as count/min/max so a
  large checkpoint grid cannot flood an agent context.
- JSON uses `allow_nan=False`; all array cells are normalized before encoding.
- Text is generated from the same payload as JSON so labels and axis order cannot
  drift.
- The reporting module imports the viewer backend only after CLI mode selection and
  never imports `app.py`, Tkinter, or Matplotlib.
- `inspection.py` owns selectors and use-case state; `renderer.py` owns only
  Figure/Agg drawing; `errors.py` owns stable error payloads. The renderer is
  imported only for explicit export.

## Mutability Profile

Presentation wording and additional backward-compatible payload fields may evolve.
Stable contracts are schema identification, row/column generation meaning, exact
selector resolution, one inference pass for `both` or one case, bounded standard
JSON, clean stdout, read-only workspace behavior, collision-free explicit evidence,
and no GUI import.
