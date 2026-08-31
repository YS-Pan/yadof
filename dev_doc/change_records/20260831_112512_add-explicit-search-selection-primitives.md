# Add explicit search, prediction-binding, and selection primitives

## Context

Real-only optimization, GPSAF assistance, and posterior-assisted fallback each
owned a private pymoo generation loop. Candidate records mixed normalized design,
predicted costs, and pymoo individuals; candidate identity was not distinct from
rounded duplicate identity or durable evidence identity. GPSAF also consumed the
Stage 4 prediction DTO only through a component-private adapter, and pymoo's
random refill could loop without an explicit exhaustion outcome.

A workspace program therefore could not compose search, prediction, selection,
and real evaluation as separate operations, preserve a deterministic branch, or
inspect the state transition that produced a real population. Retaining three
full-real loops also made fallback parity and failure boundaries difficult to
prove.

## Decision

Make backend-neutral, frozen values the public optimization boundary:
`SearchCandidate`, opaque `SearchState`, `CandidatePool`, `PredictedCostRows`, and
`CandidateSelection`. Candidate ID, rounded duplicate key, and optional source
evidence ID are separate values. State operations are functional: each operation
clones private pymoo/RNG state and returns a new revision, so callers can continue
or deterministically fork without mutating the input state. Search state is
generation-local and deliberately non-pickleable; durable resume remains the
generation-boundary reconstruction from recorded real history.

Split generation work into explicit `prepare_search`, search/warm-start,
prediction binding, survival selection, beta advancement, pool composition, and
full-real-search primitives. Pymoo continues to own algorithms, ask/tell,
operators, reference directions, and survival. Candidate exhaustion now raises
`InsufficientCandidatePoolError` after bounded ask and random-refill attempts.

Bind deterministic surrogate means only through `PredictedCostRows`, with exact
pool/state/candidate ordering, objective width, and finite-value checks. A real
`CostTable`, posterior `JointObjectiveSamples`, or unbound `SurrogatePrediction`
cannot be supplied to selection. Predicted values remain transient and never
become recorder, dataset, checkpoint, or history evidence.

## Implementation

- Added `optimize/primitives.py` with the backend-neutral values and explicit
  prepare, continue/fork, search, warm-start, bind, select, advance, combine,
  compose, and full-real operations. Private state is capability-token protected,
  bound to strategy/problem/generation/snapshot identity, and refuses pickle.
- Kept concrete pymoo objects in `optimize/pymoo/backend.py`; added bounded
  candidate generation diagnostics, typed exhaustion, current-survivor access,
  and a single survival adapter. No pymoo import was added to the lightweight
  parent package path.
- Reduced `RealSearchStrategy` to the shared full-real primitive plus the common
  real evaluator. GPSAF alpha, beta, exploration, and population composition now
  use the explicit pool/prediction/selection state transitions. Its retained
  component support is limited to one typed legacy prediction-binding edge.
- Reused prepare/search/full-real primitives for posterior candidate pools and
  fallback while preserving posterior readiness, joint-sample, qNEHVI hard-stop,
  and soft-fallback semantics as a separate capability path.
- Added a runtime-checkable deterministic prediction-provider protocol and let
  PCA/SVD recover the exact caller-supplied Stage 4 state before producing its
  typed selection prediction.
- Exported the new public values and operations from `yadof.optimize`, updated
  architecture, module/file blueprints, terminology, and advanced user guidance,
  and added direct contract and adapter tests.

The refactor did not change GA/NSGA-III numerics, GPSAF alpha/beta/gamma settings,
PCA/SVD mathematics, qNEHVI eligibility, recorder semantics, or the real
evaluation boundary. In particular, `gamma` remains in validation, identity, and
diagnostics and still does not add selection mathematics.

## Verification and evidence

- The accepted Stage 4 wheel first passed the focused pre-change baseline
  (`45 passed in 6.62s`). A seeded golden harness with SHA-256
  `2BD48AF6084045D5FE43B82B962C098B61991C9C41FDB0E9BE12EA4D250E17CE`
  froze GA, NSGA-III, real-only, and GPSAF populations and alpha/beta/exploration
  diagnostics. The post-change installed wheel reproduced all values and ordering
  exactly.
- Direct/focused installed-wheel acceptance passed `55 passed in 6.75s`; the
  broader optimize/surrogate set passed `116 passed in 19.19s`. After the final
  wheel build and force reinstall, the complete installed-package suite passed
  `429 passed in 94.96s` with a fresh absolute pytest base temp and cache disabled.
- Import origin was
  `.venv/Lib/site-packages/yadof/__init__.py`, with the checkout `src` absent from
  `sys.path`; all five public primitive value types imported from
  `yadof.optimize`.
- Fresh smoke workspace `temp/20260831_110042-stage5-benchmark-smoke` completed
  collected/valid at `40/40/40/40`, zero issues/anomalies/publication failures,
  and two completed training events. Its total benchmark elapsed time was
  `19.950418 s`; final hypervolume `0.019393302` was descriptive only.
- The single planned measured workspace
  `temp/20260831_110042-stage5-benchmark-measured` completed collected/valid at
  `2000/2000/2000/2000`, with zero issues, anomalies, or publication failures.
  The optimization command took `649.1225638 s`, result runtime was
  `649.4805222 s`, and end-to-end benchmark elapsed time was `697.618195 s`.
  Descriptive final hypervolume was `0.17932445257445517` and was not an
  acceptance or scientific-improvement gate.
- All 20 generation and training events completed. Generation 0 was real warmup;
  generations 1--19 used the surrogate. Every surrogate generation bound and
  selected exactly 90 primary candidates plus 10 exploratory candidates. Search
  state revisions were recorded (`2` for warmup and `16` thereafter), all 20 state
  IDs were distinct, and duplicate rejection, random-refill attempt, and refill
  totals were all zero.
- All 20 checkpoint aliases, namespace manifests, and model artifacts existed,
  were nonempty, and matched their recorded hashes. State/artifact digests were
  each distinct across 20 generations, provenance digests were nonempty, and the
  checkpoint state/training-data digest sets exactly matched the training-event
  sets.
- Smoke and measured strategy files were byte-identical with SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`;
  their seed, baseline, execution policy, and strategy matched, with only the
  planned `20 x 2` versus `100 x 20` budget and workspace-local paths differing.
  Every generation reported GPSAF `gamma=0.5`.

## Automatic TODO check

Reliable-recording consistency was naturally in scope because all paths end in
the common real evaluator. The explicit primitives never call the recorder, all
predictions remain typed transient data, evaluator/recording failures are outside
soft fallback catches, and the measured run published all 2,000 rows without a
publication failure.

The bounded redundancy check was also naturally in scope. The duplicate
real-search orchestration was removed from `RealSearchStrategy` and GPSAF
assistance in favor of the shared full-real primitive; GPSAF and posterior retain
only prediction/acquisition-specific adapters whose failure semantics differ.
No further in-scope wrapper or branch could be proved redundant without erasing a
public or retained-capability boundary.

The release-marker check found only explicit Stage 7 retained-capability wording,
not incidental edition numbering. The component-configuration check found no
second component settings entry: pymoo/GPSAF settings still originate in factory
kwargs, while population, random seed, duplicate archive precision, and surrogate
training lag remain declared core campaign policy. All four recurring automatic
TODOs remain active.

The repository entered Stage 5 clean at
`7249298bfdb04201bbba773f305548eadb651a9b`; there were no pre-existing user
changes to include.
