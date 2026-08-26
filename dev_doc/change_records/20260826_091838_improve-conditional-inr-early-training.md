# 2026-08-26 09:18 - Improve Conditional-INR Early Training

## Context

- The frozen hard `test-com` performance pilot completed every planned evaluation,
  but GPSAF + conditional-INR ended at cumulative hypervolume `0.0082307239`
  versus `0.0091581359` for paired NSGA-III after 36 real evaluations per arm.
- The first usable GPSAF generation relied on a model trained from only 12 points
  in a 20-dimensional design space. Standard size-N bootstrap gave each ensemble
  member only about 63% distinct rows on average.
- Field-balanced query subsets were sampled independently on every training step.
  They were without replacement only within one step, so large rawData fields could
  repeat coordinates while leaving other coordinates unseen. The benchmark field
  table contained 95,937 modeled queries, while several objective calculations
  depended on sparse grid positions.
- With the default maximum lag of two generations, the three-generation fast pilot
  used conditional INR only in generation 2 and used the generation-0 checkpoint;
  the generation-1 training request arrived while generation-0 training was still
  pending and was not queued.

## Change

- Replaced independent per-step field query draws with one seeded permutation per
  field and a deterministic cross-step cursor. Allocation remains field-balanced
  and without replacement within a step, but now covers every field coordinate
  before repeating its ordering.
- When bootstrap is requested but fewer than two real samples per input dimension
  exist, every ensemble member now sees all real rows. Independent member seeds
  retain ensemble diversity; configured bootstrap begins automatically once the
  sample threshold is reached.
- Changed the package-default `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` from two to one
  generation so the model used by selection cannot remain two generations stale.
- Added focused tests for deterministic cross-step coordinate coverage and sparse
  high-dimensional row preservation, and updated the current user, architecture,
  configuration, and surrogate blueprints.

## Rationale

- Both changes preserve the real-only, full-rawData, equal-field contract. They do
  not restore task weights, synthetic targets, optimizer trust from training error,
  or ensemble-spread selection.
- Early real evidence and rare rawData coordinates are information-limited; drawing
  duplicates or discarding unique design rows spends training compute without
  increasing support. Independent initialization remains sufficient for an
  uncalibrated diagnostic ensemble during this sparse phase.
- A one-generation default lag improved the fast-task model's evidence cutoff while
  retaining staggered training for evaluations long enough to overlap it. The
  setting remains workspace-configurable because blocking cost depends on task
  timing.

## Verification

- Baseline run
  `20260826_005604-conditional-inr-baseline-a60b47a47421`: 72/72 completed,
  GPSAF cumulative HV `0.0082307239`, NSGA-III `0.0091581359`, surrogate training
  time `14.6888` seconds.
- Coordinate-coverage-only run
  `20260826_010459-conditional-inr-cyclic-coverage-349c7fb981d1`: 72/72 completed,
  GPSAF cumulative HV `0.0082555018`. Its sampled generation-2 cost absolute error
  against the generation-0 checkpoint fell from about `0.1733` to `0.1241`.
- Final run
  `20260826_011320-conditional-inr-sparse-bootstrap-53b43fb47c56`: 72/72 completed,
  GPSAF cumulative HV `0.0114840344`, paired NSGA-III `0.0091581359`, and surrogate
  training time `20.5257` seconds. GPSAF HV was 39.5% above the original GPSAF
  pilot and 25.4% above the paired NSGA-III value in this run.
- Exact repeat
  `20260826_011527-conditional-inr-final-repeat-a2e4fb775ee9` reproduced both final
  HV values exactly; training time varied to `24.4443` seconds.
- These are descriptive one-case, one-seed, 36-evaluation-per-arm pilot results,
  not a significance claim or a substitute for the 2,000-evaluation-per-arm formal
  performance tier.

## Impact

- Sparse high-dimensional campaigns retain more real design support during early
  model fitting and large rawData fields receive deterministic coordinate coverage.
- Cheap fast tasks may block more often for model freshness; expensive or
  distributed evaluations can still overlap training, and workspaces may select a
  different non-negative lag.
- Old checkpoints remain inference-compatible. The changed default lag contributes
  to the normal strategy semantic signature, isolating default-config state; a
  workspace that explicitly retains its old lag may continue to recover compatible
  weights and will use the new training behavior on later publications.

## Follow-Up

- The public audit still does not expose checkpoint training cutoffs, so its matrix
  cannot distinguish in-sample, overlap, and forward rows. A formal multi-seed
  performance run is still required before making a broad algorithm-ranking claim.
- Full-rawData reconstruction error can remain weakly coupled to objective ranking
  when task cost uses sparse extrema or grid positions. Any future remedy must stay
  within the real-only, task-agnostic rawData contract unless a separately approved
  benchmark gate changes that policy.
