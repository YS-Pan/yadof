# Blueprint: installed package and workspaces

## Intent

yadof is a task-agnostic installed framework. Stable code and read-only resources
live under `src/yadof`; user-editable task inputs and runtime output live under an
explicit workspace. There is no source-runtime namespace. Normal use is
AI-agent-first: a human user directs an installed coding agent, which reads packaged
user guidance, authors the workspace, and applies the user's execution limits plus
the documented cost/risk policy through the same public CLI/API available to direct
users. Bounded low-cost execution can be delegated; long or consequential runs
need an explicit user request.

Workspace task flexibility remains live during a campaign. A user may correct or
redefine cost, complete optimization composition, parameters, configuration, and task execution code between
generations. The next generation uses one coherent current snapshot and rebuilds
affected derived state. The framework detects changes for cache invalidation and
provenance but does not decide whether two task versions are scientifically
equivalent; the user owns whether old evidence should remain.

## Main contract

`normalized variables -> rawData -> current cost`. Evaluations and surrogates emit
rawData; costs and normalized history are derived from stored evidence and current
task definitions. New task objectives independently map fixed physical thresholds
to dimensionless `[0, 1]` minimization costs; they never use observed-history bounds.
Fast, local, and distributed backends share result/persistence and failure-shape
contracts. Fast is memory-backed and has no durable per-candidate job folder;
local/distributed remain file-backed prepared-job transports.

## End-to-end responsibilities

1. Resolve one explicit workspace and immutable effective configuration.
2. Snapshot both complete source roots, fresh-load parameter/objective definitions,
   and construct the one workspace-owned strategy without global module leakage.
3. Generate normalized candidates through that strategy and materialize a self-contained assigned
   parameter snapshot per job.
4. Execute task-owned `evaluation.py` in reusable isolated fast workers, or
   `workflow.py` locally/directly through HTCondor; prepared workflows' fixed
   lifecycle runs through package `worker_misc` support.
5. Require schema-versioned direct `rawData/*.npz`; package worker support packages
   them as flat `rawData.zip` and Condor returns the zip rather than the directory.
6. Normalize all outcomes into ordered `JobResult` rows with per-individual
   diagnostics and explicit file/memory evidence backing plus an optional real job
   path.
7. Own every started population through one generation-scoped `EvaluationHandle`;
   wait exposes only finalized rows, cancellation stops unfinished transport work,
   and close releases every backend/session/snapshot obligation.
8. Normalize local process-tree and HTCondor ClassAd resource evidence, then reuse
   one smoke/preceding-generation calibration for scheduler requests or local
   worker-count planning.
9. Atomically record raw variables, rawData, lifecycle/provenance metadata, and
   lightweight campaign metadata, applying bounded backpressure and waiting for a
   population's evidence before later evaluation.
10. Recalculate normalized variables and fixed-threshold `[0, 1]` objective costs
   through the current workspace task definition.
11. Train/recover workspace-local rawData-first surrogate models and use predictions
    only to screen candidates that still receive real evaluation.
    The opt-in PCA/SVD baseline keeps its truth-encoding reconstruction oracle
    outside this path; deployable use maps normalized parameters through ridge
    coefficients and reports no uncertainty capability.
12. For an explicitly composed posterior-assisted consumer, require typed
    performance/calibration/transferability readiness, create one persistent
    schema-bearing function sampler, stream complete named rawData draws by
    candidate chunk through the generation snapshot's frozen cost interpreter,
    retain only joint objective samples/validity diagnostics, and never publish
    predicted rawData.
13. Keep discrete qNEHVI exploitation separate from explicit real exploration and
    send their one combined unique population through the common real evaluator;
    scientific blockers and soft selection failures use a complete real-search
    fallback without changing GPSAF.
14. Maintain a versioned surrogate evidence and release program. CAE representation,
    prediction, coordinate, and resource results remain continuous, case- and
    use-case-specific evidence rather than one all-cell performance gate. Exact
    posterior capability still fails closed when its schema/state/calibration or
    acquisition semantics are unusable. Same-budget arms may be compared in valid
    pairs as they become available; a missing or unavailable posterior arm remains
    unresolved without invalidating deterministic comparisons. Structural evidence
    never proves optimization benefit, and no study changes the package template
    default without a separate user decision.

Steps 1, 2, 3, 7, and 10 are generation-scoped rather than campaign-frozen.
Shape-preserving parameter-range/level and fixed-width objective changes rebuild
affected derived history for the next generation; mechanically unusable old records
are isolated, while a mere source-fingerprint change never excludes evidence by
itself. Parameter identity/count and objective count remain stable in the current
hot-change contract; structural dimension changes are future work.

## Boundaries

- Package: framework APIs, CLI, defaults, job/worker support, templates, adapters,
  tools, embedded docs, and all behavior invariant across optimization tasks.
- Workspace: `config.py`, fixed `submit/`, evaluate-side `job_template/`, jobs, records, checkpoints, logs,
  tool output, and optional user-created task/debug/export directories;
  workflow/cost code contains only behavior that changes with the task. Extra
  directories are not implicit prepared-job inputs.
- Examples: Git-tracked reference workspaces under `examples/`; never runtime write
  targets or distribution members.
- Benchmark distribution: independent `yadof-benchmark/` project with its own
  installed package, console command, code-first workspace, self-describing
  baselines, documents, and focused tests. One timestamped workspace owns one
  `benchmark.py` and one direct execution. Another execution uses another
  workspace; there is no run container, resume, attempt array, or copied code
  snapshot. Runtime/package/account provenance is recorded once before cell work.
  Planning expands semantic comparisons into short ordinal `cells/cNNNN`.
  Omitted budgets resolve to seed 101, population 200, and 50 generations, or 15
  generations when any selected strategy declares `slow_surrogate=True`.
  Explicit budgets are preserved. Individual simulation failures are counted and
  may be tolerated when attempted budget, finite evidence, task contracts,
  generation-0 pairing, and final metric remain valid. Same-case paired
  comparisons require matching baseline input digest, planned/attempted budget,
  and initial normalized population. A terminal cell publishes aggregate evidence
  before FIFO refill. Cell concurrency and baseline worker concurrency remain
  separate. Results/reports/visualizations are direct workspace outputs with
  short filenames. Inspect is bounded/read-only and uses current-workspace timing
  only. Windows AI-agent launches require host execution under the interactive
  human account because detach cannot change a sandbox process's session.
  A visible detached console is hosted persistently after the benchmark command
  exits so the user can review its final terminal state and close it explicitly;
  hidden detach remains noninteractive and automatic.
  Structural evidence is integration-only; performance output is descriptive and
  single-seed performance remains exploratory. The distribution depends on
  yadof's public surface, never the reverse. Root `dev_doc/` exclusively owns
  repository-wide context documents, toDos, obsolete handoffs, and change records.
- Admin: deployment and configuration guidance under `admin_tool/admin_doc/`, with
  executable administrator resources in sibling directories under `admin_tool/`.
- Tests: installed-package generic contracts under `tests/`.

## Package module map

- `workspace`, `config`, and `task_loader` establish explicit isolated context.
- `job_template` interprets task-owned parameters, rawData, and costs.
- `job_template` also owns exact named rawData schema templates and the thin frozen
  current-cost projector used by derived posterior samples; it does not own a
  posterior model or acquisition policy.
- `evaluate_manager` owns immutable prepared batches, backend-neutral handle state,
  preparation, fast/local/HTCondor transport, cancellation/cleanup, result shape,
  retries/timeouts, and recording handoff.
- `recorded_data` owns durable evidence and current-history queries.
- `optimize` owns the campaign engine and public composition seam; its `gpsaf/` and
  `pymoo/` subpackages physically isolate GPSAF coordination and the mature-backend
  adapter. `optimize/primitives.py` owns backend-neutral immutable search candidate,
  pool, predicted-cost, selection, and generation-local continuation values while
  pymoo retains concrete algorithm/ask/tell/survival ownership. The workspace owns
  complete strategy composition.
- `surrogate` owns a lightweight public component API plus a backend-neutral joint
  rawData function-sampler protocol; its `conditional_inr/`
  subpackage physically isolates rawData prediction, uncertainty intervals,
  modeling, scheduling, metadata, and checkpoints. Its independent
  `linear_subspace/` package owns deterministic per-field PCA/SVD, ridge
  parameter prediction, oracle diagnostics, and a separate checkpoint namespace.
- `tools` and `cli` are optional user-facing orchestration/inspection layers. The
  CLI keeps parser/routing in `main.py` and isolates standalone smoke safety and
  optimization-run presentation in `smoke.py` and `run.py`; tiny lazy dispatchers
  keep help, version, and documentation commands independent of runtime imports.
  `tools.cost_viewer` is a reusable read-only history-analysis/report/plot leaf
  with its own nested developer documentation and a compatibility facade.
  `tools.surrogate_viewer` is an explicitly launched, read-only GUI/text inspection
  leaf with its own nested developer documentation and optional dependency group.
- `_resources` contains immutable templates, adapter references, documentation, and
  the small worker helper copied into jobs.

## Data ownership

Workspace raw variables and rawData are durable source truth. Workflow lifecycle
metadata and execution provenance are durable diagnostics. Costs, normalized
variables, surrogate predictions, and objective-specific windows are derived. This
separation permits cost-policy changes without repeating compatible simulations.
Posterior rawData draws, their projected objective samples, and acquisition values
are transient derived state. They never become record envelopes or a second history
and cannot be used as real-evaluation truth.

Prepared jobs own local/distributed task execution inputs and outputs but not
durable history. Fast logical evaluations own no durable intermediate directory. The
installed package owns framework logic but no mutable user data. HTCondor execute
scratch is ephemeral and administrator-controlled.

## Distributed payload and output rule

A prepared job may contain task models/assets plus direct task/support files, but it
must not contain a yadof package, wheel/archive, compatibility bootstrap, generated
worker config, copied framework config tree, or `calc_cost.py`. The assigned
parameter snapshot imports no yadof. `workflow.py` is the direct executable and
`worker_misc.py` is the only package-owned worker support file.

The execute-side `rawData/` is flat. `rawData.zip` contains `.npz` basenames at its
root, and explicit Condor output transfer returns that archive plus individual
metadata. Submit-side code strictly restores/validates it before persistence.

## Failure, concurrency, and recovery

Parameter assignment, fast worker/task, preparation, workflow, timeout, submit,
hold, archive, validation, recording, and cost failures remain per individual. A
failed fast worker/process tree is killed and replaced. Standard memory/disk holds may trigger bounded
fresh-cluster retries; other failures do not. Population order/objective width is
stable regardless of completion order.

Cancellation before start is resource- and evidence-free. Cancellation after start
preserves completed rows and records each unfinished row as `cancelled`; it never
turns recorder failure into optimizer infinity. Open handles are generation leases:
the next snapshot is rejected until they close, and session shutdown cancels/waits
them before recorder and snapshot cleanup.

An OS campaign lock plus atomic rename protects immutable segment publication;
checkpoint publication retains its own atomic replacement. Background surrogate
training is at most one task per workspace. Resume uses current compatible evidence
and checkpoint signatures and never reads another workspace. Concurrent optimization
campaigns use different workspaces; one workspace is one active campaign/write
domain.

## Invariants

All stateful public APIs take a workspace. Package resources are never runtime write
targets. Config precedence is defaults < workspace < temporary override. Fresh task
loading isolates same-named helpers between workspaces. Failures become diagnostics
and correct-width infinity. Wheel/sdist exclude examples, workspaces, and runtime
artifacts.

Additional invariants: workflows write evidence rather than cost; distributed
workflows do not import yadof; rawData directories and transport archives are flat;
local/distributed execution converge before recording; core runtime never depends on
optional tools or administrator code; historical documents do not override current
architecture/blueprints. Task modules call package support for invariant behavior,
and package modules do not hard-code task-variable simulator or objective policy.
Developer maintenance performs a bounded pre-completion check of active automatic
toDos against already in-scope evidence; recurring automatic toDos remain active
after a single matching occurrence. Every developer context pass enumerates all
`dev_doc/context/` filenames without opening their contents; a full read requires a
task-relevant filename match, and expiry is assessed only on explicit user
instruction.

A simulator-specific Python/Conda environment remains an external runtime. The
packaged `chrono_com.py` resource implements the PyChrono v1 boundary: it selects
only an absolute configured interpreter, launches task-owned child code with an
isolated environment/scratch/process tree, and accepts only bounded versioned JSON
plus no-pickle schema-valid NPZ. Windows launches add only the selected runtime's
standard native-DLL directories to the child environment copy; they do not select
an interpreter through PATH or mutate parent/user/machine state. The boundary
cannot move yadof into the child runtime or let task objects/costs/partial evidence
cross.

## Verification boundary

Generic tests use installed wheels, temporary neutral workspaces, mocked scheduler
interfaces, and synthetic adapters. They cover artifact membership, read-only
site-packages, workspace isolation, job payload exclusions, direct workflow submit,
flat zip restoration, persistence, optimization, surrogate recovery, and CLI/tools,
including lazy viewer registration and deterministic viewer backend/aggregate
contracts plus schema-versioned text/JSON reporting when its optional dependencies
are available. The packaged PyChrono adapter conformance suite uses fake child
processes to lock protocol, diagnostics, environment, failure, timeout, and
concurrency semantics without a PyChrono installation. Live pools/simulators and
concrete physical assertions remain integration tests outside the default package
suite and follow the user workflow's cost- and risk-based execution policy.

The independent benchmark distribution has a focused structural suite below
`yadof-benchmark/tests/`. Temporary workspaces, fake commands, and public result
fixtures verify initialization, default budget resolution, slow-surrogate
generation limits, short paths, direct cell/postprocessor output, one-time runtime
provenance, installed-driver execution, simulation-error tolerance, report
validity, read-only inspection, CLI surface, and persistent visible-detach receipts
without a simulator. Real benchmark execution remains subject to user workflow
cost/risk and host-account authority. Separate artifact allowlists keep benchmark
resources out of the yadof wheel and include them in the yadof-benchmark wheel.
