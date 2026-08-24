# File blueprint: src/yadof/evaluate_manager/finalizer.py

## Intent

- Give fast, local, and distributed evaluations one candidate-finalization path
  whose evidence must enter the reliable campaign recorder.

## Functionalities

- Normalize every backend outcome into an ordered `JobResult` with campaign and
  generation-snapshot provenance.
- Validate and own file-backed or memory-backed rawData exactly once, calculate the
  current cost from the generation snapshot, and record validation/admission timing.
- Convert rawData/current-cost failures into candidate errors with stable objective
  width.
- Hand the owned envelope to `CampaignSession` only after the current cost is
  finalized; capacity backpressures and recorder failure propagates.

## Invariants

- The finalizer may wait for recorder capacity but not for a specific segment write;
  the dispatch boundary performs the complete durability wait.
- A finalized result is never allowed to advance the campaign without its durable
  evidence; envelope-construction/admission failure is a recording error.
- Backends do not contain independent persistence branches.
