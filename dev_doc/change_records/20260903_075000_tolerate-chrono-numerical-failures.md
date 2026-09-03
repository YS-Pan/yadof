# Chrono numerical failures and failure summaries

## Context

The seed-101 perfect-surrogate experiment completed five cells but stopped the
Chrono GPSAF cell during its fourth generation. A divergent ball state reached
the task helper's generic finite-input guard and was propagated as a fatal oracle
contract error. Geometry failures and individual timeouts already had a distinct
per-candidate failure path. The perfect summary callback could handle missing
results, but the runner never invoked it after a failed cell.

## Change

- The packaged Chrono task checks simulator-produced positions, velocities,
  reactions and histories and raises the existing typed simulation error for
  numerical divergence. API and shape errors retain their explicit failure.
- Reaction retrieval no longer turns arbitrary interface errors into a zero load.
- Oracle prediction audit records failed candidate indices, normalized parameters
  and error text separately from formal history and evaluation budgets.
- Workflow postprocessing accepts an explicit `run_on_failure` boolean. The
  perfect preset opts in; ordinary callbacks retain complete-collection behavior
  and are marked skipped after incomplete cells. Successful summaries never
  override the failed campaign status.
- User/developer documentation explains error isolation, summary policy and a
  fresh Chrono-only paired rerun. Both package versions remain unchanged.

## Validation

Installed-package tests cover nonfinite numerical states, errors that must still
propagate, continued GPSAF generations after failed oracle/real candidates,
unchanged formal counts, reproducible audit fields and summary generation after
a failed cell. Task-local acceptance evidence records the wheel fingerprint,
full-suite results, smoke, real historical reproduction and measured launch.

The installed benchmark suite passed 64 tests and focused acceptance passed 14.
Three historical normal designs retained bitwise-identical costs. A validation
copy of the prior three-generation history completed generation four with 200
additional formal attempts, 65 failed oracle simulations out of 1080, zero
contract errors and 180 selected/real bitwise matches. The earlier rare divergent
state did not recur in that check; an explicitly separate controlled NaN injection
after a real Chrono solver step verified the numerical-failure path in both the
oracle and formal evaluator. Failed and successful injected-control candidates
retained ordered, bitwise-matching costs without contaminating measured history.

The separate required complete-preset smoke completed all 18 cells and all nine
paired initial designs. All 3600 planned attempts were recorded: 3252 completed
with finite costs and 348 reported simulation failures. Every cell remained
valid and the campaign completed successfully. The smoke validates installation
structure; the later-generation and controlled-fault checks above validate
GPSAF/oracle continuation beyond the initial design.

## Scope

No GPSAF selection mechanism, optimizer parameter, valid-candidate physical
model, cost function or stopping threshold is retuned. The new measured workspace
runs the two Chrono arms from fresh paired history; earlier results are retained.
