# 2026-08-26 18:47 - Use All Real Rows for Ensemble Mean

## Context

- Complete single-seed performance run
  `20260826_1605-conditional-inr-standard-score-v2` completed all six cells and
  all 12,000 attempted evaluations. It retained all three paired comparisons;
  204 failed candidates were confined to the two Chrono arms and no generation
  had all-infinite objectives.
- Final cumulative hypervolume for GPSAF + conditional-INR versus NSGA-III was
  `0.25636212` versus `0.26094822` on Chrono, `0.29089272` versus `0.25536912`
  on SAW, and `0.27152774` versus `0.20683099` on test-com. These are paired
  descriptive values for one seed, not a statistical ranking.
- At the 20 fixed generation checkpoints, GPSAF led 12 times on Chrono, led at
  the final seven checkpoints on SAW, and led at every checkpoint after the
  common initial generation on test-com. Every surrogate generation used the
  latest one-generation-lag checkpoint.
- The formal run's first usable models already had 83--100 retained real rows,
  so the prior twice-input-dimension guard enabled ordinary size-N bootstrap
  immediately. Each member therefore retained only about 63% distinct real rows
  on average even though ensemble spread is diagnostic and does not affect GPSAF
  candidate selection.

## Change

- Changed the package and `INRTrainConfig` defaults so every independently
  initialized ensemble member trains on every retained real row.
- Kept `SURROGATE_INR_BOOTSTRAP_MEMBERS = True` as an explicit opt-in. Its
  real-only sampling and sparse-history guard are unchanged.
- Added an installed-package regression test at a 100-row training size to prove
  that all three default members receive the complete real design matrix.
- Updated current user documentation and the conditional-INR modeling blueprint.

## Rationale

- Independent initialization already provides member diversity. Because GPSAF
  currently discards member spread, dropping unique measured rows cannot provide
  an uncertainty benefit to selection and needlessly weakens the fitted ensemble
  mean.
- This variant isolates evidence coverage from the standard-score architecture.
  The user requested a second later benchmark variant that retains bootstrap and
  aggregates the best member costs; the two complete runs will be compared
  sequentially rather than competing for the same GPU and simulator resources.

## Impact

- The authoritative path remains normalized variables to each predicted rawData
  structure to current `submit/calc_cost.py`. No variables-to-cost model, task
  weighting, synthetic target, or recorded-evidence mutation was added.
- The changed default is part of the surrogate's controlled training
  configuration and therefore changes the normal strategy/state signature. A
  workspace that explicitly opts into bootstrap retains the prior resampling
  behavior.
- Network tensors and inference semantics are unchanged, so no architecture
  version bump is required.

## Verification

- Built `yadof-0.4.1-py3-none-any.whl`, force-reinstalled it into the outer
  workspace `.venv`, and confirmed imports resolve below
  `.venv/Lib/site-packages/yadof` with both package and train-config bootstrap
  defaults equal to `False`.
- Focused installed-package policy tests: `12 passed in 2.32s`.
- Complete installed-package suite: `258 passed in 74.10s`.
- Standalone benchmark suite: `55 passed in 2.41s`.

## Follow-Up

- Run the complete six-cell, one-seed `performance` suite for this full-evidence
  ensemble-mean variant.
- After collecting that run, implement the user-requested bootstrap plus
  optimistic member-cost aggregation variant, run the same complete suite, and
  compare both immutable results with paired NSGA-III before choosing the final
  implementation.
