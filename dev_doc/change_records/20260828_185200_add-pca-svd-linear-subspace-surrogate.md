# Add PCA/SVD linear-subspace surrogate

## Context

The historical rank-32 PCA benchmark encoded validation rawData directly and was
therefore a useful representation oracle, not a deployable candidate surrogate.
The active TODO authorized an explicit reusable module but not a default change,
posterior claim, simulator run, formal benchmark, or long training campaign.

## Change

- Added the single public `pca_svd()` factory and private `linear_subspace/`
  implementation package.
- Defined centered per-field PCA and uncentered per-field truncated SVD with
  explicit rank clamp/sign conventions, exact named schema round trips, and a
  deterministic multi-output ridge parameter-to-coefficient predictor.
- Kept `fit_codec()`/`evaluate_oracle()` diagnostic-only and separate from GPSAF's
  deployable path; the component exposes zero-width intervals and no posterior.
- Added independent scheduling, exact-state identity, atomic no-pickle checkpoint
  publication/recovery, generic package tests, and an explicit recorded-data-only
  four-arm diagnostic runner guarded against accidental measured execution.
- Sealed the solver/resource audit and v11 preregistration without changing v4/v5
  evidence or the v10 release receipt.

## Decision

`pca_svd()` is the one authoritative configuration path. Public defaults use rank
16 while the new diagnostic plan fixes rank 32. Torch low-rank was selected because
the bounded 2000 x 26645 audit made exact NumPy SVD 4.12 times slower and about
2.21 GB RSS; Torch remains lazy and comes from the existing surrogate extra.

## Impact

The starter template, conditional INR, hierarchical CAE, GPSAF mechanics, current
cost authority, recorded evidence, and posterior-assisted fail-closed behavior do
not change. Three-case measured scientific results remain separately gated and the
active TODO is not archived by this implementation-only change.
