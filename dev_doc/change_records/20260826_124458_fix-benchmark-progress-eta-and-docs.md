# 2026-08-26 12:44 - Fix Benchmark Progress, ETA, And Developer Docs

## Context

- The prior benchmark progress repair updated Rich tasks atomically, but a real
  2,000-evaluation cell still appeared to remain at zero and the global row lost
  its trailing status fields in an ordinary-width terminal.
- Diagnosis against run `20260826_021119-full-performance` showed that yadof was
  emitting valid positive evaluation snapshots. Fixed-width Rich columns hid the
  cell identity and counts, while integer percentage rendering and a floor-filled
  bar made early positive progress indistinguishable from zero.
- Unattended benchmark/optimization loops need a read-only estimate of how long a
  running benchmark is likely to take before the next scheduled inspection.
- The benchmark developer guide was a small monolithic supplement and did not
  provide the current-view contracts and targeted maintenance routes used by the
  root yadof `dev_doc/`.

## Change

- Replaced the multi-column progress layout with compact, unconstrained status
  text; shortened the bar; showed explicit `completed/total`; rendered fractional
  percentages below ten percent; and guaranteed one filled bar cell after the
  first positive evaluation.
- Centralized yadof progress parsing so the live renderer and timing estimator
  consume the same snapshot contract.
- Extended `benchmark inspect` with elapsed time, active command/cell progress,
  inactivity age, estimated remaining seconds, estimated completion UTC,
  confidence, evidence-basis counts, and an explicit caveat.
- Estimates combine sealed cell wall times with progressively broader case/arm
  cohorts. When the active optimize log has a current yadof snapshot, the estimate
  projects its remaining fraction without scanning unbounded logs.
- Expanded `benchmark_automation/dev_doc/` into skill contracts, C4 and 4+1
  architecture views, module/file blueprints, terminology, and change-record
  routing. Updated the benchmark operator guide, agent guide, and root development
  documentation to point to those contracts.

## Rationale

- Progress is useful only when an early nonzero event is visibly different from
  zero and the identity/count/status fields survive normal terminal widths.
- Run-local immutable plans and sealed attempts are the most reliable available
  source for an ETA. The estimate remains advisory because initialization,
  failure, retries, postprocessing, and heterogeneous optimization phases are not
  perfectly predictable.
- A scheduled follow-up needs one bounded read-only command whose output carries
  both terminal state and enough timing evidence to choose the next check.
- Split current-view documents reduce the need to rediscover invariants from a
  large implementation file and make benchmark changes follow the same
  documentation discipline as yadof itself.

## Impact

- The benchmark automation suite passes 53 tests with fresh external pytest state,
  including an actual narrow Rich-console rendering of the first evaluation and a
  deterministic live-progress ETA scenario.
- A read-only inspection of the existing performance run produces an ETA without
  mutating or restarting the run. Its currently active cell has no optimization
  snapshot yet, so the estimate correctly reports low confidence and an
  inactivity age rather than claiming precise progress.
- Installed yadof package code and packaged resources did not change. The
  benchmark remains a source-checkout tool, so no wheel build or reinstall is
  required.

## Follow-Up

- Scheduled automation can call `benchmark inspect`, reschedule while the state is
  running, and collect/report only after a terminal state. It should treat low
  confidence or a large inactivity age as a diagnostic signal, not as a precise
  completion promise.
