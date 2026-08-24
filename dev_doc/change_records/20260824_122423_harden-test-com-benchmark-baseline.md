# 2026-08-24 12:24 - Harden the test_com benchmark baseline

## Context

The first `test_com` replacement corrected nearly flat costs, but made the
opposite calibration error for benchmark use: pure NSGA-III approached its plateau
within 2,000 evaluations. That left too little difficult search for a constrained
2,000-evaluation comparison to expose conditional-INR value.

## Change

- Added and selected immutable baseline `synthetic-antenna-4dc66b0f60bf`; retained
  both prior identities unchanged as historical provenance.
- Added a task-local four-objective Pareto direction and a shared non-separable,
  multimodal loss involving all 20 variables, then encoded the resulting positions
  into the existing physical rawData contract.
- Recalibrated the state-aligned S11, beam-gain, back-lobe, and axial-ratio anchors
  to the new physical mapping.
- Added static distribution evidence, a SAW comparison, and three complete
  200-individual by 50-generation pure NSGA-III validations.
- Kept the packaged yadof adapter and the benchmark performance budget unchanged.

## Rationale

Difficulty belongs to the frozen optimization problem, not to the reusable yadof
framework. A new baseline identity preserves reproducibility and keeps old run
reports interpretable. Retaining the common 2,000-evaluation performance budget
tests both arms in the deliberately pre-convergence regime, while separate
10,000-evaluation runs demonstrate the pure-search convergence scale.

## Impact

At 2,000 evaluations the three new pure NSGA-III runs reached only HV
`0.1513`-`0.1692`, with best average cost `0.3321`-`0.3439`. They continued to
HV `0.4347`-`0.4409` at 10,000 evaluations and still gained `5.13%`-`5.94%` over
the final ten generations. All 30,000 real evaluations were recorded without
failures or timeouts, and no individual had average cost below `0.1`.

## Follow-Up

The two benchmark arms were not compared in this calibration task. A future
performance campaign should create a new run identity using the selected baseline
and retain the existing paired-seed validity checks.
