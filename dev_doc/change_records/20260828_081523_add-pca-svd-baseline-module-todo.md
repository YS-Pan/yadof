# Add PCA/SVD Baseline Module TODO

## Summary

Added a standalone manual TODO for promoting PCA/SVD from a benchmark-local
reconstruction diagnostic into reusable yadof surrogate modules while preserving a
separate oracle reconstruction baseline.

## Documentation decision

The handoff records the user's explicit approval required by the active hierarchical
CAE TODO to add a PCA/SVD factory. It distinguishes the existing validation-data
projection, which measures only low-rank representation capacity, from a deployable
`normalized parameters -> coefficients -> complete rawData` component suitable for
explicit GPSAF composition.

The plan fixes rawData-first reconstruction, per-field PCA versus uncentered
truncated-SVD semantics, a simple ridge coefficient predictor, independent state and
semantic identity, fail-closed posterior behavior, frozen-evidence preservation, a
new preregistered benchmark path, and installed-wheel acceptance. It does not change
the current default strategy, reopen any failed scientific gate, authorize a
measured campaign, or modify source/runtime behavior.

## Impact

- Added one active manual TODO under `dev_doc/toDo/`.
- No architecture, blueprint, terminology, user workflow, source code, test,
  dependency, benchmark preregistration, frozen receipt, or package behavior changed.
- Future implementation must update current-view documentation only as each planned
  behavior becomes real.

## Validation

- Read the root development and documentation contracts, all current architecture
  views, current terminology and active TODO context, and the directly relevant
  project/surrogate/test blueprints.
- Inspected the current benchmark PCA implementation, frozen v4/v5 plan/result,
  v10 missing-arm declaration, public surrogate component seam, and GPSAF prediction
  consumption before writing the handoff.
- Kept oracle representation evidence separate from deployable prediction and
  optimization claims.
