# File blueprint: src/yadof/optimize/gpsaf/phases.py

## Intent
- Implement the GPSAF algorithm phases while leaving campaign orchestration and
  real-evaluation recording to the common optimization layer.

## Functionalities
- Build and score surrogate-assisted candidate populations.
- Apply GPSAF exploration, exploitation, and replacement rules.
- Return normalized populations through the common strategy contracts.

## I/O Format
- Consumes common optimization history/problem descriptions and pymoo-backed
  search objects.
- Produces normalized candidate rows and GPSAF diagnostics used by
  `assistance.py`.

## Non-Obvious Techniques
- Pymoo integration is imported from the sibling `optimize.pymoo` package; shared
  optimization state and result types remain in the parent package.

## Mutability Profile
- GPSAF phase policy may evolve, but real evaluation and durable history must
  continue to pass through common optimization components.
