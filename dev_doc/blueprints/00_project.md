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
7. Normalize local process-tree and HTCondor ClassAd resource evidence, then reuse
   one smoke/preceding-generation calibration for scheduler requests or local
   worker-count planning.
8. Atomically record raw variables, rawData, lifecycle/provenance metadata, and
   lightweight campaign metadata, applying bounded backpressure and waiting for a
   population's evidence before later evaluation.
9. Recalculate normalized variables and fixed-threshold `[0, 1]` objective costs
   through the current workspace task definition.
10. Train/recover workspace-local rawData-first surrogate models and use predictions
    only to screen candidates that still receive real evaluation.
    The opt-in PCA/SVD baseline keeps its truth-encoding reconstruction oracle
    outside this path; deployable use maps normalized parameters through ridge
    coefficients and reports no uncertainty capability.
11. For an explicitly composed posterior-assisted consumer, require typed
    performance/calibration/transferability readiness, create one persistent
    schema-bearing function sampler, stream complete named rawData draws by
    candidate chunk through the generation snapshot's frozen cost interpreter,
    retain only joint objective samples/validity diagnostics, and never publish
    predicted rawData.
12. Keep discrete qNEHVI exploitation separate from explicit real exploration and
    send their one combined unique population through the common real evaluator;
    scientific blockers and soft selection failures use a complete real-search
    fallback without changing GPSAF.
13. Bind integrated release to a versioned fail-closed acceptance record. Structural
    mechanism regression may proceed while scientific gates are blocked, but the
    formal seven-arm same-budget matrix may start only after representation,
    coordinate, exact-state posterior/applicability calibration, remaining numeric
    thresholds, installed-wheel identity, and campaign authority all pass. A
    successful structural run never promotes an experimental head or changes the
    package template default.

Steps 1, 2, 3, and 9 are generation-scoped rather than campaign-frozen.
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
  `yadof_benchmark` package, console command, code-first workspace API,
  self-describing packaged baselines, user/developer documents, and focused tests.
  Workspace `benchmark.py` files select complete optimization strategies and
  declare any number of comparison matrices plus postprocessors. Adding an
  algorithm requires no runner registry or source change. A new run snapshots the
  complete Python workflow/resources, driver, selected clean baseline workspaces,
  and strategy inputs. Every exact materialized cell passes `yadof check` before
  execution, and resume uses only run-owned files. Public yadof rows become
  arbitrary-arm long results and optional descriptive reference deltas; opaque
  optimization metadata is retained without algorithm-specific interpretation.
  Run-local attempt evidence retains the complete cell ID, while materialized
  yadof execution workspaces use stable digest directories to keep external-
  simulator paths compact; an all-infinite generation fails the benchmark cell
  rather than becoming an empty comparison result. The distribution depends on
  yadof's public surface, never the reverse. Root
  `dev_doc/` exclusively owns repository-wide toDos, obsolete handoffs, and change
  records.
- Admin: deployment and configuration guidance under `admin_tool/admin_doc/`, with
  executable administrator resources in sibling directories under `admin_tool/`.
- Tests: installed-package generic contracts under `tests/`.

## Package module map

- `workspace`, `config`, and `task_loader` establish explicit isolated context.
- `job_template` interprets task-owned parameters, rawData, and costs.
- `job_template` also owns exact named rawData schema templates and the thin frozen
  current-cost projector used by derived posterior samples; it does not own a
  posterior model or acquisition policy.
- `evaluate_manager` owns preparation, local/HTCondor transport, result shape,
  retries/timeouts, and recording handoff.
- `recorded_data` owns durable evidence and current-history queries.
- `optimize` owns the campaign engine and public composition seam; its `gpsaf/` and
  `pymoo/` subpackages physically isolate GPSAF coordination and the mature-backend
  adapter. The workspace owns complete strategy composition.
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
after a single matching occurrence.

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

The independent benchmark distribution has a focused unit suite below
`yadof-benchmark/tests/`. Its initialization, Python workflow loading, baseline
discovery, planning, snapshot, execution, postprocessing, recovery, report, and CLI
tests use fake commands and do not start a simulator. Real `run` and `resume`
operations remain subject to the user workflow's cost/risk authorization. Separate
artifact allowlists keep benchmark resources out of the yadof wheel and include
them in the `yadof-benchmark` wheel.
