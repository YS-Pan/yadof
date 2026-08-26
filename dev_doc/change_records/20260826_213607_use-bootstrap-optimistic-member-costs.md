# 2026-08-26 21:36 - Use Bootstrap with Optimistic Member Costs

## Context

- Complete single-seed performance run
  `20260826_1851-conditional-inr-full-evidence-mean` tested the variant where
  every independently initialized ensemble member saw all retained real rows and
  GPSAF used the cost of the ensemble-mean rawData reconstruction.
- All six cells completed. The run attempted all 12,000 planned evaluations,
  completed 11,787, and recorded 213 failed candidates, all in the two Chrono
  cells: 142 for NSGA-III and 71 for GPSAF. There were no timeouts,
  all-infinite generations, excluded pairs, or public-API issues.
- Final cumulative hypervolume for GPSAF + conditional-INR versus its paired
  NSGA-III arm was `0.27241114` versus `0.38081006` on Chrono,
  `0.48370779` versus `0.45582636` on SAW, and `0.24739780` versus
  `0.22127482` on test-com. These are paired descriptive values for one seed.
- Across the 20 generation checkpoints, GPSAF tied the initial Chrono checkpoint
  and lost the other 19, ending `-0.10839892` behind with a largest deficit of
  `-0.17292717`. On SAW it led at generations 3, 19, and 20, ending
  `+0.02788143` ahead after a largest deficit of `-0.14831974`. On test-com it
  tied generation 1 and led generations 2--20, ending `+0.02612297` ahead.

## Change

- Restored seeded bootstrap training as the package and `INRTrainConfig` default.
  The existing sparse-history guard still keeps all rows visible until at least
  two real samples per normalized input variable are available.
- Changed conditional-INR population prediction so every ensemble member
  independently reconstructs rawData and passes that reconstruction through the
  current task cost function. The per-objective minimum member cost is returned as
  the optimistic point prediction and the member minima/maxima remain the reported
  cost intervals.
- Removed the previous prediction-time member exception suppression. A member that
  cannot complete the required rawData-to-cost path now fails surrogate selection,
  allowing the existing GPSAF generation fallback to use real search instead of
  silently aggregating only a subset of the ensemble.
- Kept `predict_raw_data()` as an ensemble-mean rawData reconstruction API; only
  optimizer-facing population cost aggregation changed.
- Added regression coverage for default bootstrap rows, per-member rawData-to-cost
  calls, per-objective optimistic aggregation, and GPSAF's use of the surrogate's
  primary point costs. Updated current user and developer documentation.

## Rationale

- Variant A showed that improving support coverage for a mean point estimate did
  not address Chrono selection error. Bootstrap diversity becomes actionable only
  when GPSAF uses the member outcomes rather than discarding their envelope.
- Per-objective minima deliberately form an optimistic vector and may combine
  objectives from different members rather than represent one member's joint cost
  vector. This is the requested policy. The configured real-search exploration
  quota and mandatory real evaluation of every selected candidate limit its risk.
- Keeping the aggregation inside conditional INR preserves generic GPSAF behavior:
  other surrogate components continue to control the meaning of their own primary
  point costs and intervals.

## Impact

- Every member preserves the authoritative path `normalized variables -> rawData
  -> current task cost`; there is still no direct variables-to-cost model, task
  weighting, synthetic rawData target, or mutation of recorded evidence.
- The bootstrap-default change is part of the controlled training configuration
  and therefore changes the normal state signature relative to Variant A.
- Network tensors and checkpoint artifact shapes are unchanged, so no model
  architecture-version bump is required. The optimizer-facing meaning of the first
  `predict_population()` tuple element changes from mean-rawData cost to optimistic
  member cost.

## Verification

- Built `yadof-0.4.1-py3-none-any.whl`, force-reinstalled it into the outer
  workspace `.venv`, and confirmed imports resolve below
  `.venv/Lib/site-packages/yadof` with both package and train-config bootstrap
  defaults equal to `True`.
- Focused installed-package conditional-INR policy tests: `13 passed in 3.16s`.
- Complete installed-package suite: `259 passed in 73.50s`.
- Standalone benchmark suite: `55 passed in 2.32s`.

## Follow-Up

- Run the complete six-cell, one-seed `performance` suite for this bootstrap plus
  optimistic member-cost variant.
- Collect and report that immutable run, compare it with the full-evidence mean
  variant and paired NSGA-III arms, then retain the better final implementation.
