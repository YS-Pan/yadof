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

The module owns generic fast/local/distributed evaluation, HTCondor, optimizer, and surrogate policy.
Task variable shape, objective definitions, simulator/project names, frequencies,
credentials, and adapter-specific scientific settings remain in workspace task files
or deliberately supported worker environment entries.

Local evaluation defaults to a worker cap of eight, resource autodetection enabled,
and a 15% host reserve. The cap remains a positive integer. Autodetection and reserve
settings are independently validated bool/fraction values. Existing HTCondor
CPU/memory/disk request and calibration settings also provide the per-job bootstrap
hints for local planning because both backends execute the same workflow.

Fast evaluation separately defaults to eight reusable workers, host-capacity
autodetection, a 15% reserve, and explicit one-worker CPU/memory/scratch-disk
declarations. `FAST_EVALUATION_SCRATCH_DIR` resolves from the workspace like other
path settings and must not overlap task, jobs, or recorded-data paths. Fast policy
does not reuse HTCondor request fields.

Recorder policy defines the segment candidate cap/byte target, maximum one-candidate
size, complete unpublished candidate/byte budgets, consecutive-write-failure circuit
breaker, and bounded shutdown timeout. Validation enforces positive finite values
and cross-field bounds. A campaign freezes these storage policy values and the
recorded-data path at session creation; generation task semantics may still reload.

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
