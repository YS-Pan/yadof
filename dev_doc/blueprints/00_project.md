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
- Source-checkout benchmark: Git-tracked runner, frozen baselines, strategy
  templates, bounded reports, and focused tests under `benchmark_automation/`;
  downloadable with the repository, outside `src/yadof`, and never a wheel/sdist
  member. Baselines are addressed as
  `baselines/<provider>/<task>-<12-hex-fingerprint-prefix>`, separating the
  simulator/adapter identity from the optimization-task identity. Generated runs
  use its ignored default or an explicit disjoint output root; agents use
  `temp/benchmark/<task-id>`, and automatically named run directories begin with
  a digits-only UTC `YYYYMMDD_HHMMSS` date/time prefix. The current non-surrogate
  arm is named for its concrete NSGA-III algorithm. Measured cells deliberately
  permit 32-way fast oversubscription, run the baseline's common `postprocess.py`
  and one cost view after optimization, keep every cell's prefixed visualization
  artifacts directly in one flat run-level directory, retain a bottom cell-progress
  bar in interactive terminals, and expose final cumulative HV as a compact
  algorithm-labeled table without mixing it into JSON stdout.
- Admin: HTCondor pool/slot-user/deployment material under `admin_tool/`.
- Tests: installed-package generic contracts under `tests/`.

## Package module map

- `workspace`, `config`, and `task_loader` establish explicit isolated context.
- `job_template` interprets task-owned parameters, rawData, and costs.
- `evaluate_manager` owns preparation, local/HTCondor transport, result shape,
  retries/timeouts, and recording handoff.
- `recorded_data` owns durable evidence and current-history queries.
- `optimize` owns the campaign engine and public composition seam; its `gpsaf/` and
  `pymoo/` subpackages physically isolate GPSAF coordination and the mature-backend
  adapter. The workspace owns complete strategy composition.
- `surrogate` owns a lightweight public component API; its `conditional_inr/`
  subpackage physically isolates rawData prediction, uncertainty intervals,
  modeling, scheduling, metadata, and checkpoints.
- `tools` and `cli` are optional user-facing orchestration/inspection layers.
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

The source-checkout benchmark has a separate focused unit suite below
`benchmark_automation/tests/`. Its planning and preflight acceptance paths are
bounded and do not start a simulator; measured suites require the benchmark's
explicit prerequisite and cost/risk authorization. The package artifact allowlist
keeps the benchmark absent from wheel and sdist even though it is tracked in the
repository.
