# File blueprint: src/yadof/surrogate/hierarchical_cae/data_filtering/frequency.py

## Intent

- Implement the hierarchical CAE's task-neutral, versioned `frequency` filtering
  mode without importing a concrete simulator or executable task callback.

## Functionalities

- Validate JSON-safe filter identity, ordered diagnostic rules, field selectors,
  weights, and optional task-declared frequency/morphology thresholds.
- Resolve each design in priority order: explicit version-matched assessment,
  declarative task diagnostics, configured frequency fallback, then declared
  uniform/error behavior.
- Produce design-by-field loss/shared weights, private-residual targets,
  applicability labels, regime strata, and bounded source counters.
- Round-trip frequency filters through mappings for public configuration, semantic
  identity, and checkpoint recovery.

## Invariants

- No Chrono/task field names or thresholds are hard-coded.
- Frequency features never rewrite or smooth source rawData and run only as a
  declared missing-diagnostic fallback.
- Spectral high-frequency energy is computed from field values, not by selecting a
  physical frequency-axis band.
- Mode selection and the default uniform view belong in sibling `modes.py`.
