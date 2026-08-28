# Benchmark Architecture Index

The benchmark is a source-checkout experiment orchestrator around an installed
yadof distribution. Its invariant chain is:

```text
editable declared inputs
  -> no-write plan and preflight
  -> immutable run spec, matrix, execution/baseline/strategy/history snapshots
  -> sequential isolated cell attempts
  -> public-yadof collection
  -> descriptive report
```

Runtime visibility follows a parallel read-only chain:

```text
child yadof snapshots -> timestamped progress events -> live cell/global bars
immutable plan + frozen prior-run timings + completed wall times + active event tail
  -> inspect timing/ETA
```

The runner never changes algorithm meaning, reads yadof private state, ranks arms,
or treats an ETA as scientific evidence. A run may continue while another process
calls `inspect`; inspection reads atomically published state and append-only command
artifacts without taking execution ownership.

Resume imports the run-owned `benchmark_runtime` snapshot. Current source,
package, wheel, and artifact digests are provenance only. An unfinished legacy
run without a complete execution snapshot requires explicit restart or migration;
completed legacy evidence remains inspectable and reportable.

A versioned acceptance/release preregistration may additionally close the path
from planning to formal execution. It binds inherited scientific evidence, the
complete required comparison matrix, threshold seals, installed-package identity,
and campaign authority. Structural suites can validate wiring while this gate is
closed, but their success cannot add a missing arm, mark calibration transferable,
authorize a performance run, recommend a strategy, or change package defaults.

- [C4 context](c4_context.md): people and external systems.
- [C4 containers](c4_container.md): modules and data flow.
- [C4 components](c4_component.md): implementation responsibilities.
- [Logical view](4plus1_logical_view.md): identities, state, and invariants.
- [Process view](4plus1_process_view.md): execution, progress, ETA, recovery.
- [Development view](4plus1_development_view.md): source/docs/tests and dependency rules.
- [Physical view](4plus1_physical_view.md): filesystem and process layout.
- [Scenarios](4plus1_scenarios.md): concrete operator/agent workflows.
