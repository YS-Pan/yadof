# 2026-08-30 07:43 - Complete PCA/SVD measured evidence and archive the TODO

## Context

The opt-in `pca_svd()` module, oracle/deployable separation, GPSAF lifecycle,
generic tests, documentation, and installed-wheel acceptance had already been
completed. Its manual TODO remained active until SAW, Chrono, and synthetic
antenna produced new 1000/2000-design measured evidence.

The authorized yadof-benchmark 0.2.0 workspace
`../temp/20260829_220837-pca-svd-measured-20260829` completed all three simulation
cells, but its workflow postprocessor failed with `name 'false' is not defined`.
The one-off Python source had used the JSON token `false` in three pre-test receipt
values. The failure occurred after all codec/deployable fits and validation work but
before the pre-test gate was written or test rawData was loaded. The original
benchmark therefore correctly remains terminal `failed`.

## Change

- Froze a separate recovery plan before test access under
  `../temp/20260830_073509-pca-svd-analysis-recovery`.
- Loaded the exact frozen postprocessor bytes and supplied only the missing module
  global `false = False`. The recovery changed no source, spec, state, plan,
  hyperparameter, partition, metric, stopping rule, or simulation result and did
  not rerun a simulator. Separate output was required because yadof-benchmark 0.2.0
  intentionally has no resume or repeat-in-place surface.
- Completed 24 logical analysis cells: three cases, two training sizes, centered
  PCA/uncentered SVD, and oracle/deployable arms. The pre-test gate passed with no
  prior test access, performance threshold, or hyperparameter change.
- Added the measured provenance, principal results, resource envelope, numerical
  limitations, and recovery digests to the completed PCA/SVD TODO, then moved it to
  `dev_doc/obsolete/`.
- Updated the active Hierarchical CAE/qNEHVI total TODO to treat PCA/SVD measured
  evidence as complete while retaining same-budget formal-suite integration in the
  seven-arm work. Updated the parked anti-noise TODO to consume the archived
  baseline without treating it as regime probability or posterior authorization.

## Measured result

All three cases used 2,800 unique result-independent designs. SAW and synthetic
antenna completed all 2,800; Chrono retained 729 failed simulations without
resampling and supplied 2,071 completed rows, including 296 of 400 test rows.

Rank-32 representation was nearly exact for synthetic antenna, moderate for SAW,
and weakest for Chrono. Across case/train/decomposition combinations, deployable
current-cost RMSE exceeded oracle RMSE by about `0.16–0.21`. PCA and SVD deployable
results were nearly identical, and increasing the planned training prefix from
1,000 to 2,000 did not produce a consistent cross-case improvement. The result
therefore identifies linear parameter-to-latent mapping as the common bottleneck
and does not justify a production default or a PCA-versus-SVD winner.

Deployable Spearman values were about `0.60` for SAW, `0.36–0.37` for Chrono, and
`0.77` for synthetic antenna. Pairwise dominance agreement was about `0.88`,
`0.52–0.53`, and `0.947`, respectively, while Pareto-set F1 remained only about
`0.28–0.38`; pairwise agreement is not interpreted as strong Pareto-front recovery.
Chrono standardized RMSE is numerically ill-conditioned because near-zero
per-coordinate training scales amplify tiny errors, so physical/relative,
current-cost, rank, and Pareto metrics carry the conclusion. A synthetic-antenna
SVD explained-energy macro of `1.000000127` is retained as a roughly `1.3e-7`
randomized-float32 numerical overshoot rather than clipped or selected upon.

Per-arm fit time ranged from `0.208 s` to `6.209 s`; test prediction ranged from
`0.049 s` to `1.546 s`. The largest measured process RSS was `6.77 GiB`, largest
CUDA allocation was `223.2 MiB`, and individual checkpoint size ranged from about
`0.313 MiB` to `12.73 MiB`. Process RSS is the sequential analysis process peak,
not incremental model allocation.

## Provenance and validation

- Frozen analysis plan:
  `26bb9407d3096b264fed529c08a89d5ee5b102fd33ac72aef07b70dc31d97a76`.
- Frozen postprocessor:
  `205c295656b2ac447bb5b4faaa477a5231c50e739c236e875dd2396401b30ae3`.
- Original spec:
  `ac12712b7e8067cc0a81abad736e26aee83b2842e368b8248d70c326f7e78ff5`.
- Recovery plan/script/receipt:
  `c7f3b925dfba2981acff8ffe182a9b197ac60f96d4c327e14a7a60dfec7c5422` /
  `7f8a6fc96ec2a1242976660dbc33af31d7be866180475176e136e98f53ff59a3` /
  `03ff3a9ad6c0bdfe8947349691648a45d9dfef17f9d7efa983bf0412cc1cefa0`.
- Recovered analysis/metrics/pre-test gate:
  `1e391cc06333f66f5dca23fa05ce04c0597abe32e269aa0122029f48abe9b971` /
  `8b945dd56ae5fc04f066014dbb2e4c41e71f7210bd59db3d7180d5b1206e1b36` /
  `c1f8d9b786ea888606aac31f4349fcd8c50c75276c80abd07119243232538075`.
- The recovery ran as `ysPan` with Python 3.13.11 and completed in `159.523 s`.
- The 48 checkpoint files written before the original failure and by the recovery
  match byte-for-byte; all 56 receipt-listed artifacts passed existence, size, and
  SHA-256 checks.
- The analysis contains 24 unique cells, 12 oracle and 12 deployable, with no
  missing key/ranking metric, no non-positive cost gap, and no oracle/selection/HV
  eligibility violation.
- Installed import verification reported yadof 0.4.2 from
  `.venv/Lib/site-packages/yadof`.
- Installed-package PCA/SVD focused tests: `11 passed in 7.63s`, with a fresh
  task-unique pytest base temp and cache provider disabled.
- This was a documentation/toDo-state closeout with no package code, tests, build
  configuration, documentation mechanism, or resource mapping change; the
  development guide's documentation-only exception therefore did not require a
  wheel rebuild or full package suite. The implementation change had already
  completed its wheel, force-reinstall, import-origin, focused, and full-suite
  acceptance.

## Impact and follow-up

`pca_svd()` remains an explicit deterministic baseline with zero-width intervals
and no posterior/readiness capability. Oracle results remain representation-only.
This closeout changes no template default, optimization recommendation, recorded
evidence, current-cost authority, or Hierarchical CAE/qNEHVI release status.

The active Hierarchical CAE/qNEHVI total TODO continues to own formal same-budget
PCA/SVD arm integration together with the blocked Hierarchical CAE, calibration,
eligible-readiness, seven-arm optimization, and release decisions. The large raw
evidence remains ignored workspace data; the hashes and scientific conclusion in
the archived TODO and this append-only record are the tracked handoff.
