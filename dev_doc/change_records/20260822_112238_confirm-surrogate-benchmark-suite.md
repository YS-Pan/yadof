# 2026-08-22 11:22 - Confirm Surrogate Benchmark Suite

## Context

- The real-only surrogate toDo was waiting for a user-confirmed production
  benchmark suite, metrics, thresholds, and acceptable tradeoffs.
- Existing workspace comments incorrectly assigned entire workspaces to control or
  surrogate-assisted roles even though the user selected them as benchmark cases,
  not experimental arms.

## Change

- Recorded the user-confirmed benchmark cases: `20260807 saw`,
  `20260811 chrono trebuchet flexible`, and `20260816 surrogate test_com`.
- Corrected the three workspace config comments so their current alpha/beta values
  describe only their current runtime profile and do not assign benchmark roles.
- Kept experimental arms, comparison protocol, clean-clone policy, metrics,
  thresholds, execution budget, and acceptable tradeoffs explicitly unresolved.
- Recorded a read-only readiness snapshot: all three workspaces pass `yadof check`;
  SAW has 20,002 currently interpretable records, Chrono has 1, and `test_com` has
  2; none currently has a trained checkpoint in the active format.

## Rationale

- Treating a workspace as a benchmark case separates problem selection from the
  experimental arm. Current configuration values must not silently settle an
  experimental design that the user has not selected.

## Impact

- No evaluation, simulator, surrogate training, history mutation, or checkpoint
  creation was performed.
- Experimental arms/protocol, metrics, thresholds, acceptable tradeoffs, and the
  bounded execution budget remain open user decisions, so the real-only surrogate
  toDo remains active.
