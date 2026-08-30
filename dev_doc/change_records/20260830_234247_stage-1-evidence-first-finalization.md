# 2026-08-30 23:42 - Commit evidence before current-cost interpretation

## Context

Real-evaluation finalization calculated current cost before handing owned rawData
to the campaign recorder. A callback exception or process loss could therefore
discard otherwise valid evidence. Queue admission also lacked a candidate-visible
acknowledgement that distinguished memory ownership from recovery-visible atomic
segment publication. Stage 1 of the authorized explicit-optimization refactor
required evidence-first ordering without sacrificing bounded batching or turning
recording failures into optimizer penalties.

The input repository was clean at
`17c3e95b3a24184977b300972661a48650632ac7` on `main`, two commits ahead of the
then-known `origin/main`. No pre-existing tracked, staged, or untracked change was
included.

## Change

- Added a population-scoped `ResultFinalizationCoordinator` shared by fast, local,
  and distributed evaluation. It validates and owns evidence, admits bounded
  groups using the existing segment count/byte targets, waits for durable receipts,
  then interprets current costs in stable population order through one frozen task
  interpreter. The existing one-row finalizer remains a facade over this path.
- Added `PublicationReceipt` and explicit pending/committed/failed evidence state
  to `CampaignSession`. Receipts carry candidate/group identity, resolve only after
  immutable segment publication, and wake with `RecordingError` when admission,
  oversize handling, retained-batch retries, or the writer fails.
- Kept completed segment records evidence-only. Normalized values, costs,
  interpretation state, failure diagnostics, and timing remain transient session
  state, so a failed callback cannot rewrite or revoke durable completed evidence.
- Bounded committed-but-uninterpreted in-memory ownership with the existing
  unpublished candidate/byte budgets. Payloads beyond that retention budget spill
  to their immutable segment references and are reloaded for interpretation.
- Unified callback exception, objective-width, and finite-value validation between
  point-in-time `calculate_cost()` and frozen `CostInterpreter.calculate_costs()`.
  Introduced public `CostNonFiniteError` and preserved the rawdata projector's
  typed `non_finite_objective` diagnostic.
- Made current-cost exception, width mismatch, `NaN`, and either infinity an
  interpretation failure. Durable evidence stays completed and replayable; the
  backend result carries cost-failure diagnostics and the optimizer adapter alone
  substitutes correct-width infinities.
- Preserved recording failure as campaign-fatal in the Condor callback path instead
  of swallowing `RecordingError` as a progress callback failure.
- Added direct tests for grouped and out-of-order receipts, ordering, state
  separation, bounded retention, all-waiter wakeup, backend adapters, cost replay,
  and subprocess loss after commit versus enqueue-only loss. Updated existing
  recording/backend/cost tests and corrected the packaged documentation artifact
  test to the repository's established `obsolete/todo` path.
- Updated current architecture, module/file blueprints, terminology, and user
  documentation with publication receipt, replay, failure, and deterministic
  callback semantics.

## Ownership and failure decisions

The existing segment writer remains the sole publisher and physical format owner.
The coordinator owns only grouping, acknowledgement ordering, and interpretation;
it does not introduce a second writer or persistence format. Queue admission is
pending, atomic rename is committed, and no new power-loss `fsync` promise is
made. A completed evidence record has no authoritative cost field. The task
snapshot owns the current interpretation identity, which permits later replay
after a callback is corrected.

Committed payload retention is an optimization rather than a durability boundary:
the exact immutable reference is always authoritative. Reusing the recorder's
count/byte budgets prevents publication backpressure from being displaced into an
unbounded interpretation queue. RawData validation failure remains an execution
failure without completed evidence; recording failure remains campaign-fatal;
cost failure is a replayable interpretation failure.

## Validation

- Built the wheel on the host, force-reinstalled it without dependencies, and
  confirmed yadof `0.4.2` imported from the outer workspace's
  `.venv/Lib/site-packages/yadof/__init__.py`.
- Focused evidence-first, loss-tolerant recording, packaged backend, task-loader,
  and projector checks passed. The final installed-package suite passed:
  `388 passed in 81.06s`, using a fresh task-unique pytest base directory with the
  cache provider disabled.
- The unchanged recording harness/input had SHA-256
  `c3f6a5cc142d80b6790701b8c39d72df1861653d490d1891853b210a16ffcd34` /
  `7ba18420708260b32bc5f31d69875d0e988685f2ada636328a6d136c6e2d233b`.
  Five pre/post 100-row repetitions each committed 100 unique rows into seven
  segments with occupancy `[16, 16, 16, 16, 16, 16, 4]`; segments/candidate stayed
  `0.07`. Median wall time improved from `0.2101266` to `0.1353709 s` (about
  35.6%), while signed commit-to-cost median changed from `-25.3994` to
  `+0.33655 ms`. Completion-to-commit median/p95 changed from
  `26.3029/42.9794` to `12.9687/19.9571 ms`. Median peak RSS changed from
  `47,587,328` to `47,607,808 bytes`; peak unpublished and committed-owned
  ownership were 16 candidates and about 1.145 MiB, below 32 candidates/32 MiB.
  All hard gates and the predetermined 15% median target passed. One post-change
  host-noise repetition reached `0.8407237 s`; it was retained, and neither the
  repetition count nor gate was changed.
- The fresh smoke benchmark completed and validated all `40/40/40`
  attempted/completed/finite evaluations. The single authorized measured run
  completed and validated all `2000/2000/2000`, all 20 generations, generation
  zero 100/100, objective/rawData contracts, and zero failed/non-finite rows. Its
  runtime was `601.8183 s` and descriptive final hypervolume was `0.2057025861`.
  Both reports were collected/valid. The identical strategy source SHA-256 was
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`;
  GPSAF `gamma=0.5` remained present in settings, identity, and diagnostics.

Evidence paths in the outer workspace are:

- `temp/stage1-recording-20260830_223600934/pre-change.json`
- `temp/stage1-recording-post-20260830_231248051/post-change.json`
- `temp/20260830_232119-stage1-benchmark-smoke`
- `temp/20260830_232119-stage1-benchmark-measured`

## Automatic TODO check

The reliable-recording consistency TODO directly triggered, and its concrete
cost-before-publication inconsistency is fixed with bounded/fatal/recovery
evidence; the recurring file remains active. A bounded review of changed source,
direct callers, tests, and docs found no safely removable incidental redundancy:
the one-row facade, the two public cost entry modes, and backend failure isolation
have distinct contracts. No component configuration key, alias, fallback, or
second settings entry was introduced. The package stays at `0.4.2`; planned
`0.5.0` references remain confined to the authorized Stage 8 roadmap rather than
becoming incidental release markers. All four recurring automatic TODO files
therefore remain active and unchanged.

## Impact

Valid real evidence now survives callback failure and parent-process loss after
commit, and a later task snapshot can reinterpret it. Result exposure waits for
durability while preserving population batching and deterministic order. The
recorded-data physical format, package version, optimization loop, surrogate
capabilities, GPSAF mathematics/settings, and public workspace configuration are
unchanged. No real simulator, full-budget local/distributed run, shared cluster,
paid service, or user evidence migration was performed.

## Follow-up

Archive the completed Stage 1 TODO, update the overall ledger, create the verified
stage commit, perform the required post-commit fetch/push decision, then
automatically read and refine Stage 2's Dataset/CostTable contract.
