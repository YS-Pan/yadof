# Architecture index

Yadof is an installed, immutable framework operating on one or more explicit,
writable workspaces. It coordinates task-agnostic optimization while leaving the
scientific model, evidence meaning, and objective policy to each workspace.

The end-to-end invariant is:

```text
normalized variables
  -> assigned task parameters
  -> task workflow or fast evaluator
  -> rawData evidence
  -> current workspace cost interpretation
  -> objective tuple
  -> durable record and optimizer state
```

## System shape

- The installed package owns cross-task mechanisms, public APIs, templates,
  adapters, execution backends, persistence, optimization components, and installed
  user/developer documentation.
- A workspace owns task definitions, configuration, jobs, evidence, checkpoints,
  logs, and tool output. Stateful operations always identify a workspace.
- Fast, local, and distributed evaluation differ in transport but converge on the
  same result, current-cost, failure, and recording boundaries.
- External simulators remain outside yadof. Task-owned adapters cross those
  boundaries using explicit, validated artifacts rather than shared Python state.
- Administrators provision software and machines through source-checkout resources
  under `admin_tool/`; those operations are outside the installed user workflow.

## Core invariants

- Raw variables and rawData are evidence. Normalized variables, costs, surrogate
  predictions, posterior samples, and acquisition values are derived views.
- Workflows never publish authoritative cost. Validated evidence becomes durably
  recovery-visible before the current workspace cost policy interprets it.
- Individual failures preserve population order and objective width and produce
  durable diagnostics. Failure to publish an accepted record stops the campaign.
- One generation uses one coherent snapshot of current task and configuration.
  Supported task corrections take effect at the next generation boundary.
- An explicit optimization program freezes its declared source set once per run
  command and owns visible generation control flow inside framework lifecycle
  scopes; task interpretation/evaluation sources still refresh per generation.
- Cross-task invariant behavior belongs in yadof; simulator-, model-, measurement-,
  and objective-specific behavior belongs in the workspace.
- Package resources are read-only and execute nodes never need to import yadof.

## Reading order

- [c4_context.md](c4_context.md): people, external systems, and the yadof boundary.
- [c4_container.md](c4_container.md): package, workspace, execution, and persistence
  containers.
- [c4_component.md](c4_component.md): major package responsibilities and dependency
  direction.
- [4plus1_logical_view.md](4plus1_logical_view.md): domain concepts and invariants.
- [4plus1_process_view.md](4plus1_process_view.md): runtime sequences and failure
  flow.
- [4plus1_development_view.md](4plus1_development_view.md): source layout and
  development dependencies.
- [4plus1_physical_view.md](4plus1_physical_view.md): deployment and filesystem
  topology.
- [4plus1_scenarios.md](4plus1_scenarios.md): representative use cases that exercise
  the architecture.

Implementation-level current state belongs in `../blueprints/`. Task-authoring
instructions belong in `../../user_doc/`. Administrator deployment procedures live
in `../../admin_tool/admin_doc/`. Completed decisions and experiment history live
in `../change_records/` or external evidence and do not form part of this mandatory
architecture reading set.
