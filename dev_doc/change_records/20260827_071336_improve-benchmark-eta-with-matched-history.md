# 2026-08-27 07:13 - Improve Benchmark ETA With Matched History

## Context

- Full performance runs were stable at roughly 8.5 ks, but early `inspect` calls
  sometimes reported only hundreds or a few thousand seconds remaining.
- Each current performance cell has one seed, so the old current-run cohort order
  usually had no same-case/arm observation. It then treated the much faster arm on
  the same case as the next point estimate; observed NSGA-III/GPSAF cell durations
  differed by roughly one to two orders of magnitude.
- The active estimate assumed elapsed command time scaled linearly with cumulative
  evaluation count. Later surrogate training made generation intervals grow, so
  70-85 percent evaluation completion materially overstated wall-time completion.

## Change

- New-run creation now shallow-scans a bounded number of immediate prior run
  directories and freezes only exact or compatible matched-cell durations in
  immutable `timing_history.json`. Exact signatures include implementation
  fingerprints; compatible signatures retain case, arm, budget, task, resource,
  host, and configuration contracts while allowing implementation fingerprints to
  change.
- ETA cohort order is now exact prior matched cell, current same-case/arm,
  compatible prior matched cell, current same arm, then declared lower bounds.
  Same-case observations from another arm and all-arm pooling are no longer point
  estimates. Median support count and relative median absolute deviation now
  inform the reported confidence.
- Every command now retains append-only `progress.jsonl` lifecycle and parsed
  progress events with UTC timestamps. The foreground owner writes and fingerprints
  the sidecar while pipe threads continue to log/enqueue only.
- Three or more completed generation intervals enable a robust non-negative
  pairwise-median duration trend. It may raise the active-cell remainder above the
  matched whole-cell prior; the cumulative linear projection remains only the
  pre-trend fallback. Older runs without sidecars retain bounded stderr parsing.
- Updated benchmark/root operator, architecture, blueprint, terminology, and agent
  routes for the new artifacts and ETA semantics. Corrected the agent guide's
  stale full-suite count from 36,000/18 cells to 12,000/6 cells.

## Rationale

- A completed cell with the same case, arm, budget, task, and machine contract is
  a substantially better wall-time predictor than an unlike algorithm that merely
  shares a case.
- Freezing history at run creation keeps repeated `inspect` calls read-only,
  bounded, reproducible, and independent of later run-directory changes.
- Timestamped generation boundaries include the quiet training/selection work
  between evaluation bursts, which cumulative evaluation percentage cannot model.
- Exact and compatible signatures separate high-fidelity repeats from useful but
  more cautiously qualified observations across algorithm/package edits.

## Impact

- The benchmark automation suite passes 60 tests with fresh external pytest state,
  including real child-stream sidecar capture, old-run stderr fallback, cross-arm
  rejection, compatible-history selection, growth-aware phase estimation, and a
  deterministic historical-session replay.
- A read-only implementation-level replay excludes the final 2026-08-26 run and
  uses its bounded matched sample from earlier runs; it predicts that observed
  8,667-second run at 8,462 seconds, an error of about 2.4 percent rather than the
  order-of-magnitude early underestimates seen in the original session.
- The bounded `structural-canary` plan still succeeds. No simulator, measured
  campaign, collection-time inference, wheel build, or yadof reinstall was needed;
  the benchmark remains a source-checkout-only tool.

## Follow-Up

- Newly created runs receive the historical snapshot and timestamped sidecars.
  Existing runs remain inspectable through their prior current-run/lower-bound and
  bounded-stderr compatibility paths, but are not retroactively mutated.
