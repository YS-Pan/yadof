# File blueprint: src/yadof/optimize/gpsaf/phases.py

## Intent
- Implement the GPSAF algorithm phases while leaving campaign orchestration and
  real-evaluation recording to the common optimization layer.

## Functionalities
- Build and score surrogate-assisted candidate populations.
- Materialize the explicit Stage 2 evidence/cost join only for components that
  expose `training_data()`, then pass it through freshness, readiness, prediction,
  and after-submit fit calls without changing legacy component signatures.
- Convert typed PCA/SVD prediction only at the component's narrow compatibility
  boundary and finish any pending fit before generation teardown.
- Apply GPSAF exploration, exploitation, and replacement rules.
- Return normalized populations through the common strategy contracts.

## I/O Format
- Consumes common optimization history/problem descriptions and pymoo-backed
  search objects.
- Produces normalized candidate rows and GPSAF diagnostics used by
  `assistance.py`.
- Consumes resolved GPSAF settings explicitly; the core training-lag policy remains
  a narrow scheduler input owned by the generation composition.

## Non-Obvious Techniques
- Pymoo integration is imported from the sibling `optimize.pymoo` package; shared
  optimization state and result types remain in the parent package.
- The after-submit callback materializes at its actual backend timing rather than
  retaining the pre-selection view; predicted rawData never enters the session.

## Mutability Profile
- GPSAF phase policy may evolve, but real evaluation and durable history must
  continue to pass through common optimization components.
