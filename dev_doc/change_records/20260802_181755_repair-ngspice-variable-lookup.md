# 2026-08-02 18:17 - Repair ngspice variable lookup

## Context

- The packaged ngspice adapter's `NgspicePlot.variable_index()` list
  comprehension had been split across an invalid attribute name, making the
  adapter source fail Python parsing.

## Change

- Restored the lookup to iterate over `self.variables` and formatted the
  comprehension as a valid readable multi-line expression.

## Rationale

- Preserve the existing case-insensitive exact vector-name lookup without
  changing its public behavior.

## Impact

- The packaged ngspice adapter is importable again. No API, documentation,
  architecture, blueprint, or task-authoring contract changed.

## Follow-Up

- None.
