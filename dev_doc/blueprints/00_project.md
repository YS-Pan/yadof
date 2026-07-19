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

## Boundaries

- Package: framework APIs, CLI, defaults, job/worker support, templates, adapters,
  tools, embedded docs.
- Workspace: `config.py`, task modules/assets, jobs, records, checkpoints, logs,
  tool output.
- Examples: Git-tracked reference workspaces under `examples/`; never runtime write
  targets or distribution members.
- Admin: HTCondor pool/slot-user/deployment material under `admin_tool/`.
- Tests: installed-package generic contracts under `tests/`.

## Invariants

All stateful public APIs take a workspace. Package resources are never runtime write
targets. Config precedence is defaults < workspace < temporary override. Fresh task
loading isolates same-named helpers between workspaces. Failures become diagnostics
and correct-width infinity. Wheel/sdist exclude examples, workspaces, and runtime
artifacts.
