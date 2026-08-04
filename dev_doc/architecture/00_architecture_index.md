# Architecture index

The system is an installed, immutable `yadof` distribution plus one or more
explicit writable workspaces. There is no repository-local runtime namespace and
no implicit "current project". Every stateful operation is scoped to a workspace.
The normal user journey is AI-agent-first: a human user directs a locally installed
coding agent, which reads the installed, version-matched user documents and prepares
the selected workspace, while the CLI and Python APIs remain the underlying
execution surfaces.

The end-to-end invariant is:

```text
normalized variables
  -> assigned job-local parameters
  -> task workflow
  -> flat rawData/*.npz evidence
  -> current workspace calc_cost.py
  -> objective tuple
  -> recorded evidence / optimizer / surrogate
```

Core architectural goals are task-agnostic expensive evaluation, resumable
rawData-first history, fast/local/distributed evidence equivalence, per-individual
failure isolation, and safe coexistence of multiple workspaces. Fast evaluation
uses reusable isolated local workers and memory-backed evidence without durable
per-candidate job folders; local/distributed retain prepared-job diagnostics. Costs and normalized
history are interpretations of evidence, not stored source truth.
Cross-task invariant behavior belongs in yadof; workspace workflow/cost files own
only behavior that varies with the selected optimization task.

The defined-but-not-yet-adapted PyChrono boundary treats a dedicated Python/Conda
runtime as an external simulator installation. Its JSON/NPZ subprocess protocol,
environment isolation, scratch ownership, failure taxonomy, and backend-equivalent
publication rules are normative even before the packaged adapter is added.

An optional read-only surrogate viewer is an installed `yadof.tools` leaf. It
consumes the same workspace records, current cost policy, and saved checkpoints
through an explicit GUI launch or terminal text/JSON reports, but it is outside
optimization execution and never publishes workspace state. Its detailed design
remains in the viewer subtree's own `dev_doc/`.

- [c4_context.md](c4_context.md): users and external systems
- [c4_container.md](c4_container.md): package/workspace/execution/persistence split
- [c4_component.md](c4_component.md): package module responsibilities
- [4plus1_logical_view.md](4plus1_logical_view.md)
- [4plus1_process_view.md](4plus1_process_view.md)
- [4plus1_development_view.md](4plus1_development_view.md)
- [4plus1_physical_view.md](4plus1_physical_view.md)
- [4plus1_scenarios.md](4plus1_scenarios.md)
- [pychrono_subprocess_contract.md](pychrono_subprocess_contract.md): normative
  task-owned PyChrono child-process boundary

For implementation-level current state, continue with
`../blueprints/10_modules/`. Historical decisions live in `../change_records/` and
must not be treated as the current contract when architecture or blueprints differ.
