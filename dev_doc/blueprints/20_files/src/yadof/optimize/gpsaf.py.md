# File blueprint: src/yadof/optimize/gpsaf.py

## Intent
- Orchestrate one GPSAF generation without owning simulator execution or surrogate internals.

## Functionalities
- Load history, resolve problem shape, and build pymoo context.
- Gate surrogate-assisted prediction through the staggered-training freshness check.
- Use the latest trained surrogate state for candidate selection when available.
- Evaluate the selected real population and pass an after-submit callback that starts surrogate training.

## I/O Format
- Returns `OptimizationResult` with population, dynamic costs, source, surrogate flag, and diagnostics.

## Non-Obvious Techniques
- This file no longer trains surrogate before candidate selection. It schedules training only after real jobs are submitted, and lets lag policy block before selection only when a model would become too stale.

## Mutability Profile
- Keep orchestration small. Candidate mechanics stay in `gpsaf_phases.py`/`gpsaf_pymoo.py`; evaluation dispatch stays in `gpsaf_misc.py`.
