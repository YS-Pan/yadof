# Restore benchmark paired metrics and validity accounting

## Context

The code-first `yadof-benchmark` rewrite retained final hypervolume but had not
restored the paired-fairness, evaluation-counting, trajectory, incomplete-evidence,
and surrogate-training presentation contract recorded in section 7 of
`dev_doc/toDo/20260829_081608_restore-benchmark-ux-and-testing-contract.md`.

## Changes

- Each cell now publishes planned, attempted, completed, and finite counts; an
  ordered normalized generation-0 population fingerprint; final HV; cumulative HV
  trajectory and trapezoidal AUC on the attempted-real-evaluation axis; and a
  separate public-metadata surrogate-training summary.
- Same-baseline/same-seed arms are valid pairs only when their frozen baseline
  digest, planned and attempted budgets, complete generation-0 fingerprint, and
  individual validity match. Invalid pairs keep their raw results, suppress paired
  reference deltas, and are named as excluded from cross-seed aggregates.
- Reports gained trajectory, pairing-validity, cross-seed aggregate, and
  surrogate-training CSVs. The main comparison table no longer presents success
  rate or optimizer wall time as an algorithm score, and no report ranks or accepts
  a strategy.
- `Benchmark.configure()` gained an optional positive finite
  `representative_generation_seconds` value. It contextualizes surrogate-training
  time against an explicitly chosen expensive generation rather than a cheap cell
  runtime and remains descriptive.
- Package/root architecture, blueprint, terminology, user/developer guides, and
  the active restoration TODO were synchronized with the restored contract.

## Verification

- Focused source structural tests: 5 passed.
- Built `yadof_benchmark-0.1.0-py3-none-any.whl`, force-reinstalled it into the
  outer workspace `.venv`, and confirmed both `yadof_benchmark` and `yadof` import
  from that environment's `site-packages`.
- Installed-package benchmark suite: 40 passed with source injection disabled, a
  fresh absolute pytest base temp, and the cache provider disabled.
- No simulator, adapter smoke, or performance campaign was executed; the tests use
  fake commands and synthetic public-record data.
