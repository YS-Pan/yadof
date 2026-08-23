# 2026-08-23 13:48 - Fix Surrogate Viewer Mapped Raw Variables

## Context

- Completed recorded-data rows expose `raw_variables` as parameter-name/value
  mappings, while the surrogate viewer iterated those mappings as though they were
  positional sequences. A task with names such as `x0` therefore failed both
  terminal summary and audit with `could not convert string to float: 'x0'`.
- JSON object ordering also placed names such as `x10` before `x2`, so relying on
  mapping iteration order would have silently changed parameter coordinates even
  if the names were numeric strings.

## Change

- Reconstruct viewer raw-variable tuples by looking up every current declared
  parameter name in declaration order.
- Isolate malformed, incomplete, and undocumented non-mapping historical rows
  through the viewer's existing tolerant history path.
- Add regression coverage for deliberately reordered mappings and for installed
  public `summary` plus cost/rawData `audit` JSON commands over a real recorded
  workspace and compatible conditional-INR checkpoint.
- Document the ordered mapping adaptation in the viewer workspace blueprint.

## Rationale

- The mapped representation is the current recorded-data contract and preserves
  parameter identity independently of serialization key order. Reusing the task
  declaration provides the only correct positional input for normalization,
  prediction, and current-cost interpretation.
- Undocumented sequence compatibility was not retained because it can conceal
  parameter-identity errors and is outside the current persistence contract.

## Impact

- Surrogate GUI loading and terminal summary/audit can consume current recorded
  histories with mapped raw variables.
- No record, checkpoint, task, report schema, or public command surface changes.
- This also resolves the viewer-consumer inconsistency exposed by the persistent
  loss-tolerant recording consistency check; immutable history remains unchanged.

## Follow-Up

- None.
