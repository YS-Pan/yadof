# File blueprint: src/yadof/optimize/gpsaf/phases.py

## Intent
- Implement the GPSAF algorithm phases while leaving campaign orchestration and
  real-evaluation recording to the common optimization layer.

## Functionalities
- Compose alpha/beta/exploration as explicit search pool -> typed predicted cost ->
  select/advance -> unique real population operations.
- Consume caller-owned explicit training data through freshness, readiness, and
  prediction for every runtime-checkable deterministic component.
- Dispatch PCA/SVD, conditional-INR, and hierarchical-CAE through the typed
  prediction protocol and bind each prediction DTO to exact pool IDs. No path
  preserves rawData/member spread in `PredictedCostRows`.
- Apply positional alpha tournaments, nearest-alpha normalized-design clustering
  of all beta candidates, per-cluster PKT and size-ratio-to-gamma replacement.
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
- Phases never materialize session evidence or own an after-submit callback;
  predicted rawData never enters the session.
- Restore the real algorithm after beta while retaining duplicate bookkeeping.
  Error scales come from explicit prequential state, never prediction intervals.
  Missing scales hold beta until an observed error exists. The tournament stream
  is deterministic per generation and separate from pymoo/random-refill streams.

## Mutability Profile
- GPSAF phase policy may evolve, but real evaluation and durable history must
  continue to pass through common optimization components.
