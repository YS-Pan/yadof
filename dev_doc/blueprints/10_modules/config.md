# Module blueprint: config

## Responsibility and precedence

`yadof.config` owns framework-generic defaults and returns immutable `LoadedConfig`.
It merges, in increasing precedence: package defaults, uppercase values in workspace
root `config.py`, then non-mutating call/CLI overrides. Every value records its
source for diagnostics. Loading one workspace never changes defaults or another
workspace.

## Validation

Unknown uppercase settings, invalid types, non-finite numbers, invalid modes,
negative/fraction violations, and missing required task paths fail eagerly before
batch work. Relative path settings resolve from the explicit workspace root and are
returned as absolute paths through the effective `WorkspaceContext`.

The module owns generic evaluation, HTCondor, optimizer, and surrogate policy.
Task variable shape, objective definitions, simulator/project names, frequencies,
credentials, and adapter-specific scientific settings remain in workspace task files
or deliberately supported worker environment entries.

## Dependencies and consumers

The module depends on workspace context only. CLI, evaluation, optimization,
surrogate, recorded-data, and tools consume one immutable loaded instance per logical
operation. Backend helper modules receive `LoadedConfig`; they do not reimplement
precedence.

## Invariants

- Defaults are immutable and repository-independent.
- Config execution is scoped to one explicit file and converts exceptions/SystemExit
  to actionable `ConfigError`.
- Temporary overrides do not rewrite workspace files.
- `describe()` exposes effective values and their provenance.
