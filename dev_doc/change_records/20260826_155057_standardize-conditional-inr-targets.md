# 2026-08-26 15:50 - Standardize Conditional-INR Targets

## Context

- Conditional INR scaled every modeled rawData query from its observed minimum to
  maximum and applied a sigmoid decoder. Training extrema therefore sat at the
  sigmoid's hardest-to-fit endpoints, while every optimizer prediction remained
  confined to the rawData envelope already observed.
- The hard benchmark history showed that GPSAF could improve SAW yet remained
  weaker than paired NSGA-III on test-com, whose objectives depend on sparse extrema
  and directional grid positions. A bounded decoder could not propose a rawData
  response beyond existing extrema even when a normalized design candidate lay in
  a promising unexplored region.
- The formal performance suite used three seeds and 36,000 attempted evaluations,
  making each result-driven iteration take about five hours. The user explicitly
  selected one paired seed for this tuning loop.

## Change

- Replaced per-query minimum/range scaling with float64 mean/standard-deviation
  scaling and retained `SURROGATE_TARGET_SCALE_FLOOR` for near-constant positions.
- Centered normalized design inputs from `[0, 1]` to `[-1, 1]` inside the encoder.
- Replaced the sigmoid decoder output with a near-zero-initialized linear standard-
  score output. Predictions are inverse-scaled to rawData before the unchanged
  current-task cost path, and may now extrapolate beyond recorded rawData extrema.
- Added model architecture version 2 to member artifacts and bumped the public
  conditional-INR component semantic version. Incompatible bounded-output
  artifacts are rejected or isolated instead of silently receiving new inference
  semantics.
- Changed the formal benchmark to paired seed `104729`: three cases, two arms, six
  cells, 100 individuals by 20 generations, and 12,000 planned attempted real
  evaluations. Updated its scale contract and regression assertion without reducing
  any cell's population or generation budget.
- Added tests for standard-score round trips/extrapolation, centered network input,
  unbounded decoder output, old-artifact rejection, and the single-seed matrix.

## Rationale

- A zero-centered target makes the decoder's initial prediction the recorded query
  mean and gives positive and negative residuals symmetric optimization support.
  Linear output removes artificial historical bounds while the standard deviation
  keeps coordinate magnitudes comparable.
- Float64 scaler artifacts avoid introducing avoidable physical-unit rounding before
  the network's float32 target tensor is formed or after its output is reconstructed.
- Explicit architecture identity is required because the state-dict tensor shapes
  did not change; shape-only loading would otherwise reinterpret old sigmoid weights
  as linear standard scores.
- One paired seed preserves equal-budget case/arm comparisons for iterative tuning
  while deliberately giving up any statistical robustness claim. Historical multi-
  seed evidence remains immutable and separate.

## Impact

- The authoritative flow remains normalized variables to predicted rawData to
  current `submit/calc_cost.py`; no variables-to-cost surrogate was introduced.
- Existing bounded-output conditional-INR checkpoints cold-train under the new
  component identity. Recorded real evidence is untouched and remains eligible for
  fitting.
- Linear extrapolation can expose model error as well as useful improvement. The
  complete single-seed formal benchmark is therefore the next acceptance gate before
  adding uncertainty or GPSAF selection heuristics.

## Verification

- Built `yadof-0.4.1-py3-none-any.whl`, force-reinstalled it into the outer
  workspace `.venv`, confirmed imports resolve below
  `.venv/Lib/site-packages/yadof`, and confirmed architecture version 2.
- Passed the complete installed-package suite: `257 passed in 74.48s`.
- Passed the standalone benchmark suite: `55 passed in 2.43s`.
- The formal performance benchmark is intentionally recorded in a later iteration;
  it is long-running evidence rather than a prerequisite for publishing this
  independently tested implementation.

## Follow-Up

- Run the complete six-cell `performance` suite and compare final cumulative
  hypervolume, generation traces, validity, prediction diagnostics, and training
  cost. Use its immutable run as the basis for the next conditional-INR or GPSAF
  change.
