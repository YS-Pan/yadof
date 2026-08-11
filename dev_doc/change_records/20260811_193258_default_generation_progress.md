# 2026-08-11 19:32 - Default generation progress

## Context

- Optimization could appear idle for long-running fast, local, or distributed
  evaluations unless the user explicitly supplied `--progress`.
- Existing progress messages described backend activity but did not summarize how
  many individuals in the current generation had succeeded, failed, or remained.

## Change

- Enabled CLI run progress by default and added `--no-progress` as the explicit
  quiet override.
- Added one backend-neutral population progress bar per generation or pre-run
  smoke. It advances on terminal individual outcomes and reports finished/total,
  successful, error, and remaining counts.
- Streamed terminal HTCondor results through an optional non-fatal callback so the
  distributed bar updates during collection rather than only after the entire
  generation returns.
- Reconciled local and distributed success counts after recording/current-cost
  calculation so record failures appear as errors without double-counting a
  population index.
- Reused one environment-enable check for both detailed messages and the population
  bar instead of retaining duplicate parsing branches.

## Rationale

- Immediate zero-state output reassures users that optimization started, while
  per-individual updates show continued activity during expensive generations.
- A common outcome definition keeps fast, local, and distributed displays
  consistent without changing evaluation order, persistence, or failure isolation.

## Impact

- CLI run defaults, evaluation orchestration, HTCondor collection callbacks, tests,
  user run guidance, architecture, and relevant blueprints are updated.
- Python API calls remain quiet unless the existing `YADOF_PROGRESS` environment
  opt-in is active.

## Follow-Up

- None.
