# Add explicit surrogate fit, state, and prediction

## Context

The PCA/SVD surrogate previously discovered its training rows by scanning a
`CampaignSession` inside component/runtime methods. Its scheduler returned a
component-specific future facade, checkpoint identity mixed materialized values
with row provenance, and deployable prediction returned an untyped compatibility
tuple. A workspace program therefore could not freeze transformed training data,
own training lifecycle, recover the exact mathematical state, or distinguish
transient deterministic predictions from recorded evidence.

## Decision

Make `SurrogateTrainingData` the owned, immutable boundary between recorded
evidence and surrogate fitting. Its semantic digest hashes canonical materialized
parameters and complete rawData content; a separate provenance digest hashes row
identity, status, lineage, and the optional transform label. Paths and labels do
not replace content identity, and lazy, masked, object, complex, structured-main,
or non-finite targets fail closed.

Expose PCA/SVD training through one framework-owned `TrainingHandle` lifecycle.
Synchronous fitting composes the same start/wait/close path, cancellation is
cooperative and cannot publish an uncommitted state, and generation/session
boundaries own open handles explicitly. Recovery receives the exact training
value and validates its content digest, schemas, settings, strategy namespace,
parameter definition, and numerical-library versions.

Return a frozen `SurrogatePrediction` from deployable prediction. It contains
ordered candidates, complete transient rawData, current-snapshot cost rows,
zero-width deterministic intervals, state/data identity, and bounded diagnostics.
It is neither posterior output nor a real `CostTable`, and prediction never enters
the recorder or optimization history.

## Implementation

- Added `surrogate/training.py` with strict evidence/cost materialization,
  canonical content and provenance digests, the typed prediction value, and the
  shared training-handle state machine.
- Migrated PCA/SVD runtime, scheduler, model, codec, types, and checkpoints to
  explicit training values and handles. Removed their implicit session scan and
  process-global executor path; checkpoint manifests now persist separate
  `training_data_digest` and `training_provenance_digest` fields.
- Generalized the campaign generation-handle registry so evaluation and training
  use declared normal/abnormal boundary policies. Normal generation completion
  waits for training; exceptional/session shutdown cancels and closes work before
  writer and snapshot cleanup.
- Added explicit PCA/SVD `training_data`, `start_fit`, `fit`, `recover`, and
  `predict` surfaces. The current GPSAF adapter freezes aligned training data at
  the actual selection and after-submission boundaries while retaining the
  existing narrow legacy tuple only for the Stage 5/8 migration sequence.
- Added read-only PCA/SVD discovery, deterministic prediction, plot, and audit
  support to the generic surrogate viewer. Old or incompatible manifests remain
  inspectable but are not guessed compatible by runtime recovery.
- Added direct coverage for materialization identity, strict rejection, handle
  races and cleanup, recovery, transient prediction, hot cost interpretation,
  recorder non-entry, GPSAF composition, and viewer behavior. Updated architecture,
  module/file blueprints, terminology, and user guidance.

Conditional-INR, hierarchical CAE, posterior capability, PCA/SVD mathematics,
recorded-data layout, and optimizer search behavior were not migrated in this
stage. GPSAF `gamma=0.5` remained unchanged.

## Verification and evidence

- Built and force-reinstalled `yadof-0.4.2-py3-none-any.whl` into the outer
  workspace environment and confirmed the installed import origin under
  `.venv/Lib/site-packages/yadof/__init__.py`.
- Direct explicit-surrogate acceptance passed `20/20`; the retained GPSAF and
  posterior-compatibility set passed `25/25`. The installed-package full suite
  passed `419 passed in 86.88s`.
- Fresh smoke workspace `temp/20260831_094259-stage4-benchmark-smoke` completed
  collected/valid with `40/40/40/40` planned/attempted/completed/finite rows, no
  issues, two completed training events, and total elapsed time `11.635633 s`.
- The one authorized fresh measured workspace
  `temp/20260831_094502-stage4-benchmark-measured` completed collected/valid with
  `2000/2000/2000/2000` rows, no issues, and no recording failures. Its evaluation
  command took `623.791692 s`; result runtime was `624.151074 s`. Descriptive final
  hypervolume was `0.21129372436533064` and was not an improvement gate.
- All 20 generation training events completed; generation 0 was warmup and
  generations 1--19 used the surrogate. All 20 checkpoint manifests and artifacts
  exist, contain nonempty separate content/provenance digests, and their content
  digest set exactly matches the training-event set.
- Smoke and measured expanded plans matched on baseline digest, seed, execution
  policy, workflow, strategy, and byte-identical strategy SHA-256
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`;
  only the authorized `20 x 2` / `100 x 20` budgets and workspace-local paths
  differed. GPSAF diagnostics reported `gamma=0.5` in every generation.

## Automatic TODO check

The reliable-recording check was naturally in scope. Explicit training only reads
committed Stage 2 rows, prediction remains transient, generation completion waits
for training handles, and shutdown still closes handles before writer/snapshot
cleanup. Direct tests and measured evidence found no pending publication escape,
invented evidence, fatal writer error, failed receipt, or prediction history entry.

The bounded redundancy check completed in the PCA/SVD path: the old implicit
session scan, mixed training-design identity, process-global future scheduler, and
parallel prediction tuple construction were replaced by the shared explicit
values/lifecycle rather than retained as dual implementations. Similar schedulers
in conditional-INR and hierarchical CAE remain intentionally untouched until
Stage 7. The release-marker check found no incidental transition label; numeric
schema/component versions remain real compatibility fields. The component-
configuration check found no `LoadedConfig` read, secondary settings entry,
unrestricted kwargs path, legacy key, or runtime fallback. All four recurring
automatic TODOs remain active.
