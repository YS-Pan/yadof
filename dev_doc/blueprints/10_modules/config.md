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

The module owns generic fast/local/distributed evaluation, HTCondor, and genuine
cross-component campaign policy. One immutable `SettingSpec` declaration per core
name owns its default, primitive validator kind, reload policy, and path policy;
defaults, legal names, description order, and path handling are derived from that
schema rather than parallel name lists.

Search operators, GPSAF phase counts, and surrogate model/backend parameters are
not core config. Their only workspace source is explicit keyword-only component
factories in `submit/optimization.py`. Removed component names fail as unknown
settings and temporary overrides cannot reach component settings.
Task variable shape, objective definitions, simulator/project names, frequencies,
credentials, and adapter-specific scientific settings remain in workspace task files
or deliberately supported worker environment entries.

The default conditional-INR freshness bound is one generation. A workspace may
set another non-negative `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` when its measured
evaluation/training timing favors throughput over newer surrogate evidence.

Local evaluation defaults to a worker cap of eight, resource observation enabled,
and a 15% host reserve. The cap remains a positive integer and is authoritative;
detected capacity never clamps it. Observation and reserve settings are
independently validated bool/fraction values. Existing HTCondor CPU/memory/disk
request and calibration settings also provide the per-job bootstrap hints for
local diagnostics because both backends execute the same workflow.

Fast evaluation separately defaults to eight reusable workers, host-capacity
observation, a 15% reserve, and explicit one-worker CPU/memory/scratch-disk
declarations. Its configured worker cap is likewise authoritative; observed
limits are diagnostic. `FAST_EVALUATION_SCRATCH_DIR` resolves from the workspace
like other path settings and must not overlap task, jobs, or recorded-data paths.
Fast policy does not reuse HTCondor request fields.

Recorder policy defines the segment candidate cap/byte target, maximum one-candidate
size, complete unpublished candidate/byte backpressure budgets, and the maximum
attempts for one failing segment. Validation enforces positive finite values and
cross-field bounds. A campaign freezes these storage policy values and the
recorded-data path at session creation; generation task semantics may still reload.
There is no lossy shutdown timeout: campaign close waits for queued and in-flight
publication.

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
- `describe()` exposes effective values, provenance, and reload policy.
