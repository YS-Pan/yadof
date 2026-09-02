# 2026-09-02 11:20 - Exclude Smoke Evidence From Optimizer History

## Context

A pre-run smoke evaluates the midpoint with `generation_index=None` and records the
real result for diagnostics and resource calibration. The optimizer history adapter
previously accepted every durable completed row with a valid cost, so that midpoint
became the only history row before generation zero. `full_real_search()` correctly
interpreted nonempty generation-zero history as a warm start, but pymoo then created
offspring around the single midpoint instead of producing a global random initial
population.

The installed 0.5.0 path reproduced the defect. A real CLI smoke followed by one
generation reported `history=1` and `search_history_policy=warm-start`. In a direct
32-parameter, four-objective NSGA-III reproduction with population 210 and seed 101,
5,242 of 6,720 candidate coordinates (78.01%) remained exactly at 0.5 and every row
kept at least half its dimensions at the midpoint. With empty optimizer history, no
candidate coordinate equaled 0.5 and every dimension covered both below 0.1 and
above 0.9.

## Change

- Restrict `history_records()` to successful committed original evidence carrying a
  generation index.
- Keep unindexed smoke evidence durable and available to general history views,
  diagnostics, and resource calibration.
- Add an installed-package regression proving that a smoke row remains readable but
  generation zero reports no optimizer history and uses the random search path.
- Document the optimizer-history boundary in user guidance, architecture,
  blueprints, and terminology.

## Rationale

Generation scope is the existing semantic distinction between optimization
population evidence and standalone calibration/evaluation evidence. Filtering at
the optimizer adapter preserves durable truth and existing smoke calibration while
preventing an operational preflight from changing the scientific search design.
Actual generation-scoped history still warm-starts recovery and resume exactly as
before.

## Impact

New campaigns that run a smoke test retain global random generation-zero
initialization. Existing generation-scoped evidence continues to influence warm
starts, duplicate archives, later offspring, and resume. No recorded segment is
rewritten or deleted.

## Follow-Up

None.
