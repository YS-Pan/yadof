# C4 package components

## Foundation

- `workspace` resolves, initializes, and validates explicit writable workspaces.
- `config` builds immutable effective campaign configuration.
- `task_loader` and `task_snapshot` isolate workspace modules and provide one
  coherent task definition per generation.
- `_resources` supplies read-only templates, adapters, worker support, and installed
  documentation.

## Task interpretation

- `job_template` owns parameter assignment, normalization, rawData validation and
  views, current-cost dispatch, and task checking.
- RawData templates describe exact named evidence fields for consumers that need a
  stable schema.
- Cost projection converts complete schema-compatible predicted rawData through a
  frozen current task interpreter. It does not own task objective policy or record
  predictions.

## Evaluation

- `evaluate_manager` freezes each `EvaluationBatch`; its backend-neutral
  `EvaluationHandle` owns created/running/cancelling/completed/failed/closed state,
  one non-daemon execution owner, ordered terminal rows, and cleanup.
- `evaluate_population()` and standalone smoke compose the same
  prepare/start/wait/close lifecycle used by explicit callers; there is no second
  synchronous dispatch path.
- Backend selection preserves population order and per-individual failure
  isolation. A common cancellation signal is interpreted by each transport at its
  own worker/process/scheduler boundary.
- Job preparation copies task inputs, assigned parameters, and invariant worker
  support into self-contained prepared jobs.
- Fast, local, and HTCondor runners own their transport, timeout, cleanup, and
  diagnostic mechanisms.
- Resource components retain backend observations and advisory capacity estimates
  without changing task evidence or clamping an explicit fast/local worker cap.
- The common finalizer owns rawData validation/ownership, bounded group admission,
  committed-receipt coordination, stable-order current-cost interpretation, and
  result construction. Handle results contain only payload-free finalized rows and
  become visible after this boundary.

## Durable evidence

- `recorded_data` owns the campaign session, workspace lock, immutable segment
  publication, tolerant discovery, identity-preserving evidence datasets, and
  task/schema-bound cost tables.
- `EvidenceDataset` keeps original candidate identity distinct from physical-design
  equality and exposes only lazy rawData handles for committed evidence.
  `CostTable` joins by row identity, preserves typed interpretation status and
  bounded diagnostics, and converts failures to optimizer `inf` only at its
  explicit optimizer adapter boundary.
- The writer bounds unpublished ownership and makes publication failure
  campaign-fatal.
- Publication receipts distinguish pending, committed, and failed evidence.
  Committed-but-uninterpreted rawData ownership reuses explicit count/byte limits;
  excess payload is read back from its immutable segment instead of entering an
  unbounded memory queue.
- Readers isolate corrupt or incompatible records without rewriting surviving
  evidence.

## Optimization and surrogate components

- `optimize` owns the campaign engine, static optimization-source inspection,
  run-level program snapshot, framework-created run/generation scopes, and common
  real-evaluation boundary. A workspace program owns the visible
  generation/data/control flow while
  scopes retain lock/session/handle/recording/metadata/commit cleanup authority.
- Its backend-neutral search primitives own immutable candidate/pool/predicted-cost/
  selection values plus generation-local next-state/fork composition. They delegate
  concrete ask/tell/survival and operators to the private pymoo adapter and rebuild
  durable resume state only from real history.
- Search, surrogate-assistance, posterior-assisted selection, and acquisition
  components remain explicitly composed rather than selected by a second global
  method registry.
- `surrogate` owns rawData-first component lifecycles, checkpoints, prediction, and
  optional posterior capabilities. Concrete models remain behind lightweight
  public contracts and lazy optional dependencies. Its public materialization
  layer identity-joins evidence/cost rows into immutable training values, separates
  exact mathematical content identity from bounded lineage/provenance, and gives
  explicit fits a generation-scoped handle lifecycle. PCA/SVD, conditional-INR,
  and hierarchical-CAE implement one runtime-checkable deterministic component
  boundary and consume caller-owned training data for freshness, prediction, and
  scheduling.
  Hierarchical CAE owns its
  training-data filtering implementations below its private package and selects
  them through one component-local mode whose default is no filtering; the current
  opt-in implementation is `frequency`.
- Posterior and readiness contracts describe derived candidate-selection
  capabilities; they do not bypass real evaluation or persistence.
- Real-only, GPSAF, and posterior fallback share one full-real primitive. Derived
  deterministic prediction, posterior samples, and real cost tables retain distinct
  types and cannot cross each other's selection boundaries.
- `task_snapshot` classifies frozen program sources away from the
  generation-reloaded interpretation/evaluation task copy. It merges program
  provenance into the complete source record while keeping the program and
  interpretation fingerprints independent.
- The integrated surrogate viewer dispatches read-only method adapters for
  conditional-INR, hierarchical-CAE, and deterministic one-member PCA/SVD
  checkpoints. It recalculates current cost and never mutates model or evidence.

## Tools and CLI

- `cli` routes explicit commands and workspace arguments.
- `tools` contains optional inspection, history, adapter-copy, and task-support
  utilities. Integrated viewer subtrees own their detailed developer documentation
  and remain outside core execution.

## Dependency direction

Core components communicate through public package exports or narrow APIs.
Evaluation may consume task and persistence contracts; optimization may coordinate
evaluation, history, and surrogate components. Core runtime does not depend on
optional tools, administrators, benchmark automation, or concrete simulator
projects.

Optional numerical backends load only after their component is selected. Workspace
task modules may import job-local files and deliberately installed dependencies,
but distributed workflows must not import yadof. Stateful public APIs accept an
explicit workspace instead of deriving mutable paths from package location.

Detailed module and exceptional-file behavior belongs in `../blueprints/`, which
is read selectively for the component being changed.
