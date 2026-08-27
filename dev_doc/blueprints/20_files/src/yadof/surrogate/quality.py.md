# File blueprint: src/yadof/surrogate/quality.py

## Intent

- Define the task-neutral, versioned quality/regime boundary used by rawData
  surrogates without importing a concrete simulator or executable task callback.

## Functionalities

- Validate JSON-safe policy identity, ordered diagnostic rules, field selectors,
  weights, and optional task-declared morphology thresholds.
- Resolve each design in priority order: explicit version-matched assessment,
  declarative task diagnostics, configured shape fallback, then declared
  uniform/error behavior.
- Produce design-by-field loss/shared weights, private-residual targets,
  applicability labels, regime strata, and bounded source counters.
- Round-trip policies through mappings for public configuration, semantic identity,
  and checkpoint recovery.

## Invariants

- No Chrono/task field names or thresholds are hard-coded.
- Shape features never rewrite or smooth source rawData and run only as a declared
  missing-diagnostic fallback.
- With no policy, all field/shared weights are one, all residual labels are zero,
  and every applicability label is smooth.
