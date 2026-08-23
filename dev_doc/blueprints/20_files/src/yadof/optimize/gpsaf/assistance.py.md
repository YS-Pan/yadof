# File blueprint: src/yadof/optimize/gpsaf/assistance.py

## Intent
- Orchestrate one GPSAF generation from injected search and rawData-surrogate
  components without owning campaign/session/recorder or simulator execution.

## Functionalities
- Receive common generation context/history/problem shape and build the selected
  lazy pymoo search context.
- Gate surrogate-assisted prediction through the staggered-training freshness check.
- Use the latest trained surrogate state for candidate selection when available.
- Evaluate the selected real population and pass an after-submit callback that starts surrogate training.

## I/O Format
- Returns common `strategy.OptimizationResult`; every accepted row passes through
  the common real-evaluation handoff.

## Non-Obvious Techniques
- This file no longer trains surrogate before candidate selection. It schedules training only after real jobs are submitted, and lets lag policy block before selection only when a model would become too stale.

## Mutability Profile
- Keep only irreducible alpha/beta/exploration and staggered-component coordination.
  Pymoo owns algorithms/operators/survival; common evaluation/history/types stay in
  `strategy.py`.
