# C4 context

## Scope

Yadof coordinates optimization around expensive workflows without owning the
scientific meaning of a task. Users or their AI agents define one writable
workspace, while the installed package provides the stable execution, recording,
optimization, and inspection mechanisms.

## People and responsibilities

- **Users** own task definitions, objective policy, optimization composition,
  campaign configuration, scientific evidence decisions, and execution authority.
- **AI coding agents** are the normal task-authoring interface. Under user direction
  they read installed user documentation, edit the selected workspace, and invoke
  the public CLI or APIs. They are not a runtime dependency.
- **Administrators** install dependencies and simulators, configure HTCondor and
  machine permissions, and maintain shared execution resources.
- **Package maintainers** own cross-task mechanisms, stable public contracts,
  packaged resources, persistence correctness, and generic tests.

## External systems

- Local operating-system processes run prepared workflows or reusable fast task
  evaluators.
- Simulators and custom programs consume assigned task values and produce
  measurements.
- HTCondor transports prepared jobs between submit hosts and administrator-managed
  execute hosts.
- External simulator Python environments, such as the PyChrono runtime, are
  separately provisioned processes rather than alternate yadof host environments.
- The filesystem stores workspace inputs, runtime diagnostics, durable evidence,
  checkpoints, logs, and tool output.
- Optional desktop and terminal tools inspect workspace evidence and model state
  without entering evaluation or persistence.

Yadof may diagnose an unavailable external dependency or scheduler, but it does not
install, configure, restart, or repair them. Those procedures belong to
`admin_tool/admin_doc/` and its sibling tools.

## System boundary guarantees

- Stateful operations never select an implicit workspace.
- The installed package is immutable at runtime; user state is written only below
  an explicit workspace or caller-selected output root.
- Task workflows create evidence, not authoritative objective values.
- Every backend converges on backend-neutral results before current-cost
  interpretation and recording.
- Failed candidates remain explicit ordered outcomes rather than disappearing from
  a population.
- Historical compatible rawData can be reinterpreted by current task cost code;
  the user decides whether combining evidence across task edits is scientifically
  appropriate.
- Predicted rawData and derived optimizer quantities never become real evidence.
- Package code owns invariant mechanisms and workspace code owns task-variable
  scientific behavior.

Wheel and source distributions contain package code and declared package resources,
but exclude runtime workspaces, models, credentials, generated evidence, and
administrator operations. A source checkout may additionally carry examples,
benchmark automation, and administrator resources that remain outside installed
runtime behavior.
