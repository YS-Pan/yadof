# 2026-08-29 11:12 - Restore Benchmark Evidence Layering

## Context

The code-first benchmark runner did not distinguish cheap fake/CLI/canary runs
from measured optimization performance campaigns. The same result and report
surfaces could therefore make a structurally useful run look like algorithm
performance evidence. Package behavior tests and recovery fault injection were
also not explicitly separated even though recovery proves resume semantics rather
than optimizer quality.

## Change

- Required every `benchmark.py` workflow to explicitly configure one run-level
  `structural` or `performance` evidence class; planning never infers it from
  population or generation counts.
- Froze that class into every cell and propagated it with fixed scope notices
  through bounded/full plan output, result rows, CSV/JSON reports, Markdown,
  workspace indexes, detached-launch receipts, and read-only inspect. Historical
  runs without the field are
  exposed as unclassified and cannot support performance conclusions.
- Marked the focused benchmark pytest suite as structural and its recovery/fault-
  injection subset separately as recovery. Both remain simulator-free engineering
  evidence.
- Documented the full-run ladder: bounded plan/check, real adapter smoke, and a
  bounded structural canary using the same baseline, strategy, interpreter, and
  external-configuration paths before separately authorized performance work. A
  benchmark incompatibility is repaired and structurally retested; a yadof root
  defect gets a separate root toDo and blocks the affected full campaign.

## Rationale

An explicit class fails closed at authoring time and remains visible when a CSV row
or workspace index is read outside its original run. Structural validation can use
real paths without being mistaken for scientific evidence, while performance runs
remain descriptive and algorithm-agnostic. Keeping the execution ladder in the
user contract respects simulator authority without embedding machine-specific
preflight or scientific policy in the runner.

## Impact

Existing editable benchmark workflows must add
`Benchmark.configure(evidence="structural"|"performance")` before they can plan a
new run. Existing immutable runs continue through their run-owned drivers; current
inspection labels older evidence without the new field as unclassified. No
population/generation minimum, paired metric, recovery behavior, or concurrency
policy from later restoration sections was implemented.

## Verification

- Parsed all 22 benchmark source/test Python files successfully.
- Built `yadof_benchmark-0.1.0-py3-none-any.whl`, force-reinstalled it without
  dependencies, and confirmed version `0.1.0` imported from
  `.venv/Lib/site-packages/yadof_benchmark`.
- The complete installed-package focused suite passed: `33 passed in 3.71s` with
  source injection removed, pytest cache disabled, and a fresh absolute base temp.
  The separately selected recovery subset passed:
  `5 passed, 28 deselected in 1.08s`.
- Installed `docs show api.md` exposed the mandatory evidence classification.
  Installed one-cell structural `check` and `plan` both returned bounded
  `writes=false` summaries with the structural-only notice; the external
  workspace's `runs/`, `reports/`, and `visualizations/` remained empty.
- No simulator, adapter smoke, structural canary, or performance campaign was
  executed as part of package acceptance.

## Recurring Checks

The bounded redundancy review found repeated parsing of the frozen workflow
evidence field inside `results.py`. One local `_evidence()` helper now provides the
historical-run fallback consistently for comparisons, cell summaries, publication,
workspace indexes, and inspect. The helper added a few lines but removed five
independent interpretations and their opportunity to drift. The in-scope diff had
no objective reliable-recording inconsistency, incidental release marker, or
component-configuration migration omission; those recurring toDos remain active.
