# Add a unified evaluation-handle lifecycle

## Context

The public evaluator previously combined candidate materialization, campaign and
snapshot ownership, backend dispatch, publication, cost interpretation, and
cleanup in one synchronous function. Fast, local, and distributed execution all
used the common finalization coordinator, but then discarded the finalized rows
and returned only positional cost tuples. There was no backend-neutral lifecycle
for future optimization programs to overlap bounded independent work, no common
cancellation capability, and no generation-scope lease preventing a campaign from
advancing while evaluation work remained open.

## Decision

Make a frozen `EvaluationBatch` and one `EvaluationHandle` state machine the sole
evaluation lifecycle. Preparation materializes and validates batch-level inputs
without allocating runtime resources. Starting creates one non-daemon owner
thread; waiting exposes one cached immutable `EvaluationResult` only after every
visible row has passed the existing durable-publication and interpretation gate.
Cancellation is a shared event with backend-specific cleanup, while framework
failures remain fatal and repeatable for every waiter.

Campaign-backed handles lease the exact current generation snapshot. A generation
cannot advance while such a handle remains open, and session shutdown cancels and
closes handles before shutting down the recording writer or removing snapshots.
The synchronous evaluator and smoke facade are compositions of
prepare/start/wait/close rather than a second orchestration path.

## Implementation

- Added `evaluate_manager/lifecycle.py` with the batch, handle, public state
  machine, timeout/cancellation/context-manager behavior, and session registration.
- Added immutable, deeply frozen `EvaluationResult` metadata and diagnostics;
  preserved ordered `JobResult` rows with committed candidate/evidence identity,
  and retained fixed-width `inf` conversion only in the `.costs` optimizer adapter.
- Changed fast, local, and Condor adapters to return finalized rows and observe one
  cancellation event. Fast and local terminate active process trees and drain
  queued candidates as cancelled; Condor stops submission, preserves already-ready
  completions, removes outstanding clusters, and records bounded cleanup metadata.
- Added the durable `cancelled` execution status and generation-scoped handle
  registry. Standalone handles own and close their session; campaign handles reuse
  the caller's exact snapshot and cannot escape the generation boundary.
- Added direct lifecycle, race, multi-waiter, process cleanup, recorder-failure,
  fake-Condor, publication visibility, identity-recovery, and synchronous-parity
  coverage. Updated architecture, module/file blueprints, terminology, and user
  guidance for the public lifecycle.

No optimizer, surrogate, parameter/objective schema, recorded-data layout, or
scheduler transport was replaced. GPSAF `gamma=0.5` remained present in the same
strategy factory, semantic identity, validation, and diagnostics path.

## Verification and evidence

- Built and force-reinstalled `yadof-0.4.2-py3-none-any.whl` into the outer
  workspace environment and confirmed imports came from
  `.venv/Lib/site-packages/yadof/__init__.py`.
- New direct lifecycle acceptance passed `10/10`; the focused evaluation,
  recording, dataset/cost, and optimization composition set passed `109/109`.
- The installed-package full suite passed `410 passed in 86.27s` with a fresh
  absolute pytest base directory and cache provider disabled.
- The fresh 20 x 2 smoke workspace was collected/valid with
  `40/40/40/40` planned/attempted/completed/finite evaluations, no anomalies, and
  elapsed time `11.545118 s`.
- The single authorized fresh 100 x 20 measured workspace was collected/valid
  with `2000/2000/2000/2000` planned/attempted/completed/finite evaluations,
  matching objective/rawData contracts, no anomalies or simulation errors, and
  elapsed time `568.137814 s` (`520.077 s` evaluation command). Descriptive final
  hypervolume was `0.16326709272848938`; it was not an improvement gate.
- Smoke and measured expanded plans matched on baseline digest, seed, execution
  policy, workflow, strategy, and strategy SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`;
  only the authorized population/generation budgets differed. Evidence workspaces
  are `temp/20260831_082851-stage3-benchmark-smoke` and
  `temp/20260831_083033-stage3-benchmark-measured`.

## Automatic TODO check

The reliable-recording check was naturally in scope. Direct tests established
that handle visibility remains after committed publication and interpretation,
recorder failure wakes all waiters as a framework failure, cancellation does not
invent evidence, and session shutdown closes handles before writer/snapshot
cleanup; no recording inconsistency remained.

The bounded redundancy check completed in `evaluate_manager/api.py`: the previous
standalone synchronous orchestration was replaced by the same public handle
composition used by explicit callers, without retaining a dual dispatch/result
path. Backend cleanup branches were retained because their process/worker/cluster
semantics are intentionally distinct. The release-marker check found no incidental
transition label, and the component-configuration check found no second settings
entry, legacy key, unrestricted kwargs path, or fallback. All four recurring
automatic TODOs remain active.
