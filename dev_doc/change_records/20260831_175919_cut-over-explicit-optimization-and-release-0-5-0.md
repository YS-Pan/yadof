# 2026-08-31 17:59 - Cut Over Explicit Optimization And Release 0.5.0

## Context

- Stages 1--7 established durable evidence, identity-preserving tables, evaluation
  handles, explicit surrogate fit/predict state, search/selection primitives, a
  workspace program pilot, and migration of every retained consumer. Stage 8 had
  to remove the closed compatibility path instead of shipping two orchestration
  systems indefinitely.
- The release also needed a copyable set of source examples, an honest 0.4.2 to
  0.5.0 migration path, an independent benchmark breaking version, and final
  installed-artifact plus representative end-to-end evidence.

## Change

- Made a literal `YADOF_OPTIMIZATION_PROGRAM` the only workspace optimization
  entry. Removed strategy/definition loading, complete GPSAF/real/posterior runner
  factories, legacy GPSAF materialization and dynamic prediction adapters, hidden
  CampaignSession training reads, and evaluation `after_jobs_submitted` plumbing.
- Kept narrow public values and primitives: program/run/generation scopes,
  evaluation and training handles, real Pymoo search, typed deterministic
  surrogate prediction, GPSAF settings/selection, posterior-assisted selection,
  qNEHVI acquisition, and explicit commit/state boundaries.
- Added five paired source-checkout-only program examples: real-only, sequential
  surrogate, evaluation/training overlap, split cost/surrogate evidence, and an
  honest blocked posterior fallback. Added their user index and a 0.4.2 to 0.5.0
  migration guide.
- Updated the starter, CLI/check contracts, architecture, blueprints, terminology,
  user documentation, active scientific handoffs, and benchmark documentation.
  Released yadof as `0.5.0`; released the explicit-only benchmark planner as
  `yadof-benchmark 0.3.0` with `yadof[plot]>=0.5.0`.

## Rationale

- A readable workspace program must own generation control flow, data conversion,
  evaluation/training overlap, fallback, and commit order. Retaining hidden
  complete-generation runners would preserve two sources of lifecycle truth and
  make checkpoint/resume behavior depend on which path happened to run.
- Selection remains side-effect free and receives typed data. Training and
  evaluation concurrency is expressed with handles, so fast, local, distributed,
  and Condor transports do not need a program-specific callback channel.
- Posterior-assisted/qNEHVI remains fail-closed. The cutover does not manufacture
  readiness evidence, change GPSAF mathematics, or claim scientific superiority.

## Impact And Evidence

- Final focused installed-wheel slices passed `188/188`; the complete installed
  yadof suite passed `450/450` in `87.90 s`; the installed benchmark suite passed
  `22/22` in `1.08 s`. AST parsing passed for all 228 Python files.
- The full package suite covered wheel/sdist allowlists, clean external wheel
  installation, package-origin immutability, `init`, read-only `check`, explicit
  starter runs, viewers, history cleanup, and failure/refusal behavior. The release
  wheels imported from the outer `.venv` site-packages, not repository `src`.
- The exact-once smoke used the same explicit PCA/SVD + GPSAF NSGA-III source as
  the measured run and completed `40/40` planned/attempted/completed/finite rows,
  with no issues or publication failures.
- The exact-once measured run used population 100, 20 generations, and seed 101.
  It completed `2000/2000` planned/attempted/completed/finite rows with zero issues,
  anomalies, publication failures, or tolerated simulation errors. It recorded 20
  complete generations, 19 successful training events and checkpoint sets over
  100--1900 rows, and 18 fresh lag-one surrogate selections. Optimization runtime
  was `645.2844323 s`; benchmark elapsed time was `691.144475 s`.
- Smoke and measured program SHA-256 was
  `4f5f876226a6076f7ea530dbc65bb927b30a80df217cff4a0ff2c7880676876b`;
  their strategy digest was
  `fcfc93949e7df8e8b61368f6d18882e2cde3d2acc716d1dcef73a4040f9933f5`.
  Workflow comparison proved the budget was the only materialized difference.
- No real simulator, paid/shared resource, or HTCondor campaign ran. The benchmark
  is orchestration and regression evidence, not an algorithm ranking.

## Automatic TODO Check

- The bounded component-configuration review found no second settings entry or
  central algorithm defaults; `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` remains core
  campaign policy.
- Removing the evaluation callback did not bypass common finalization or durable
  generation boundaries. Installed tests and benchmark diagnostics reported zero
  recording failures, so the reliable-recording TODO had no repair match.
- Old-version names occur only in explicit migration/rejection evidence and
  append-only history. Public `0.5.0`/`0.3.0` versions are real release fields, not
  incidental edition markers.
- The authorized cutover itself removed the proven redundant compatibility
  orchestration. A bounded follow-up of the touched files found no separate safe
  one- or two-file redundancy candidate, so no additional automatic cleanup was
  added.

## Follow-Up

- Future optimization work starts from literal programs and the retained narrow
  primitives; there is no compatibility alias to remove later.
- The active acquisition-protocol, qNEHVI, noise, trust-region, and hierarchical
  CAE research handoffs retain their existing opt-in or blocked scientific scope.
