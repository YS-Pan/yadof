# Architecture index

The system is an installed, immutable `yadof` distribution plus one or more
explicit writable workspaces. There is no repository-local runtime namespace and
no implicit "current project". Every stateful operation is scoped to a workspace.

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
rawData-first history, local/distributed equivalence, per-individual failure
isolation, and safe coexistence of multiple workspaces. Costs and normalized
history are interpretations of evidence, not stored source truth.

- [c4_context.md](c4_context.md): users and external systems
- [c4_container.md](c4_container.md): package/workspace/execution/persistence split
- [c4_component.md](c4_component.md): package module responsibilities
- [4plus1_logical_view.md](4plus1_logical_view.md)
- [4plus1_process_view.md](4plus1_process_view.md)
- [4plus1_development_view.md](4plus1_development_view.md)
- [4plus1_physical_view.md](4plus1_physical_view.md)
- [4plus1_scenarios.md](4plus1_scenarios.md)

For implementation-level current state, continue with
`../blueprints/10_modules/`. Historical decisions live in `../change_records/` and
must not be treated as the current contract when architecture or blueprints differ.
