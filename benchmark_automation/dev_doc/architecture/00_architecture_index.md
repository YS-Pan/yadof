# Benchmark Architecture Index

The benchmark is a source-checkout experiment orchestrator around an installed
yadof distribution. Its invariant chain is:

```text
editable declared inputs
  -> no-write plan and preflight
  -> immutable run spec, matrix, and baseline snapshots
  -> sequential isolated cell attempts
  -> public-yadof collection
  -> descriptive report
```

Runtime visibility follows a parallel read-only chain:

```text
child yadof snapshots -> live cell/global bars
immutable plan + completed wall times + active log tail -> inspect timing/ETA
```

The runner never changes algorithm meaning, reads yadof private state, ranks arms,
or treats an ETA as scientific evidence. A run may continue while another process
calls `inspect`; inspection reads atomically published state and append-only command
artifacts without taking execution ownership.

- [C4 context](c4_context.md): people and external systems.
- [C4 containers](c4_container.md): modules and data flow.
- [C4 components](c4_component.md): implementation responsibilities.
- [Logical view](4plus1_logical_view.md): identities, state, and invariants.
- [Process view](4plus1_process_view.md): execution, progress, ETA, recovery.
- [Development view](4plus1_development_view.md): source/docs/tests and dependency rules.
- [Physical view](4plus1_physical_view.md): filesystem and process layout.
- [Scenarios](4plus1_scenarios.md): concrete operator/agent workflows.
