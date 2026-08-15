# File blueprint: src/yadof/evaluate_manager/finalizer.py

## Intent

- Give fast, local, and distributed evaluations one candidate-finalization path
  whose valid cost return is independent of evidence persistence.

## Functionalities

- Normalize every backend outcome into an ordered `JobResult` with campaign and
  generation-snapshot provenance.
- Validate and own file-backed or memory-backed rawData exactly once, calculate the
  current cost from the generation snapshot, and record validation/admission timing.
- Convert rawData/current-cost failures into candidate errors with stable objective
  width.
- Offer the owned envelope to `CampaignSession` only after the current cost is
  finalized; recorder refusal or failure is non-fatal.

## Invariants

- The finalizer never waits for segment I/O.
- A valid current cost is returned unchanged whether the envelope is admitted,
  refused, later published, or later lost.
- Backends do not contain independent persistence branches.
