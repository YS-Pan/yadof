# File blueprint: src/yadof/optimize/gpsaf/phases.py

## Intent
- Implement the GPSAF algorithm phases while leaving campaign orchestration and
  real-evaluation recording to the common optimization layer.

## Functionalities
- Compose alpha/beta/exploration as explicit search pool -> typed predicted cost ->
  select/advance -> unique real population operations.
- Materialize the explicit Stage 2 evidence/cost join only for components that
  expose `training_data()`, then pass it through freshness, readiness, prediction,
  and after-submit fit calls without changing legacy component signatures.
- Dispatch deterministic PCA/SVD through the runtime-checkable selection-provider
  protocol and bind its Stage 4 DTO to exact pool IDs. Retained components use one
  narrow legacy tuple binder; neither path preserves rawData/member spread in
  `PredictedCostRows`.
- Apply GPSAF exploration, exploitation, and replacement rules.
- Return normalized populations through the common strategy contracts.

## I/O Format
- Consumes common optimization history/problem descriptions, opaque search state,
  and backend-neutral pools/selections; no pymoo object crosses this file's public
  boundary.
- Produces normalized candidate rows, next-state and bounded GPSAF diagnostics used by
  `assistance.py`.
- Consumes resolved GPSAF settings explicitly; the core training-lag policy remains
  a narrow scheduler input owned by the generation composition.

## Non-Obvious Techniques
- All ask/tell/survival ownership is reached through `optimize.primitives`; this file
  must not recreate a second duplicate/archive/refill loop.
- Alpha calls continue one search branch; beta explicitly forks and advances a
  simulated branch; exploration shares archive/RNG bookkeeping without mutating the
  alpha algorithm branch.
- The after-submit callback materializes at its actual backend timing rather than
  retaining the pre-selection view; predicted rawData never enters the session.

## Mutability Profile
- GPSAF phase policy may evolve, but real evaluation and durable history must
  continue to pass through common optimization components.
