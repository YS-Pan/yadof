# 2026-08-02 18:32 - Tolerate Unplottable Cost History

## Context

- `yadof view cost` aborted an otherwise usable 836-row workspace because one
  completed job dynamically produced non-finite costs.
- Similar row-local data and optional-annotation problems could also prevent the
  summary and PNG from showing valid historical evidence.

## Change

- Cost-history row validation now isolates malformed, non-numeric, non-finite,
  empty, combined-overflow, and minority objective-width rows while retaining their
  original evaluation-index spacing.
- The most common valid objective width is selected, ignored issues are reported in
  a bounded summary section, and optional annotation failures no longer block cost
  data.
- Objective-name lookup now falls back to deterministic generic labels when task
  names cannot be loaded.
- Tests and current user/developer documentation cover the tolerant behavior.

## Rationale

- A read-only visualization should salvage every trustworthy row it can display.
  Invalid evidence must remain visible as a diagnostic, but one bad row or optional
  annotation should not hide hundreds of valid evaluations.
- Core-history read failures and histories with no plottable row remain errors
  because no truthful visualization can be produced in those cases.

## Impact

- `view cost` and the cost half of `view all` can complete when valid history
  coexists with isolated bad rows or unavailable annotations.
- Recorded evidence, dynamic cost calculation, Pareto semantics, and plot styling
  are unchanged.

## Follow-Up

- None.
