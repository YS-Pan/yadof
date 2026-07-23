# Blueprint: installed package and workspaces

## Intent

yadof is a task-agnostic installed framework. Stable code and read-only resources
live under `src/yadof`; user-editable task inputs and runtime output live under an
explicit workspace. The old source-runtime namespace is removed.

## Main contract

`normalized variables -> rawData -> current cost`. Evaluations and surrogates emit
rawData; costs and normalized history are derived from stored evidence and current
task definitions. Local and distributed backends share job/result/persistence and
failure-shape contracts.

## End-to-end responsibilities

1. Resolve one explicit workspace and immutable effective configuration.
2. Fresh-load current parameter/objective definitions without global module leakage.
3. Generate normalized candidates and materialize a self-contained assigned
   parameter snapshot per job.
4. Execute task-owned `workflow.py` locally or directly through HTCondor.
5. Require schema-versioned direct `rawData/*.npz`; distributed workflows package
   them as flat `rawData.zip` and Condor returns the zip rather than the directory.
6. Normalize all outcomes into ordered `JobResult` rows with per-individual
   diagnostics.
7. Atomically record raw variables, rawData, lifecycle/provenance metadata, and
   lightweight campaign metadata.
8. Recalculate normalized history and objective costs through the current workspace
   task definition.
9. Train/recover workspace-local rawData-first surrogate models and use predictions
   only to screen candidates that still receive real evaluation.

## Boundaries

- Package: framework APIs, CLI, defaults, job/worker support, templates, adapters,
  tools, embedded docs.
- Workspace: `config.py`, task modules/assets, jobs, records, checkpoints, logs,
  tool output.
- Examples: Git-tracked reference workspaces under `examples/`; never runtime write
  targets or distribution members.
- Admin: HTCondor pool/slot-user/deployment material under `admin_tool/`.
- Tests: installed-package generic contracts under `tests/`.

## Package module map

- `workspace`, `config`, and `task_loader` establish explicit isolated context.
- `job_template` interprets task-owned parameters, rawData, and costs.
- `evaluate_manager` owns preparation, local/HTCondor transport, result shape,
  retries/timeouts, and recording handoff.
- `recorded_data` owns durable evidence and current-history queries.
- `optimize` owns campaign/generation candidate mechanics and GPSAF pressure.
- `surrogate` owns conditional INR training, rawData prediction, uncertainty
  intervals, audits, scheduling, and checkpoints.
- `tools` and `cli` are optional user-facing orchestration/inspection layers.
- `_resources` contains immutable templates, adapter references, documentation, and
  the small worker helper copied into jobs.

## Data ownership

Workspace raw variables and rawData are durable source truth. Workflow lifecycle
metadata and execution provenance are durable diagnostics. Costs, normalized
variables, surrogate predictions, and objective-specific windows are derived. This
separation permits cost-policy changes without repeating compatible simulations.

Prepared jobs own task execution inputs and outputs but not durable history. The
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

Preparation, workflow, timeout, submit, hold, archive, validation, recording, and
cost failures remain per individual. Standard memory/disk holds may trigger bounded
fresh-cluster retries; other failures do not. Population order/objective width is
stable regardless of completion order.

Workspace locks and atomic replacement protect JSONL/archive/checkpoint publication.
Background surrogate training is at most one task per workspace. Resume uses current
compatible evidence and checkpoint signatures and never reads another workspace.

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
architecture/blueprints.

## Verification boundary

Generic tests use installed wheels, temporary neutral workspaces, mocked scheduler
interfaces, and synthetic adapters. They cover artifact membership, read-only
site-packages, workspace isolation, job payload exclusions, direct workflow submit,
flat zip restoration, persistence, optimization, surrogate recovery, and CLI/tools.
Live pools/simulators and concrete physical assertions remain explicit integration
tests outside the default package suite.
