# 4+1 logical view

## Domain concepts

- Parameter definitions contain names, allowed ranges/levels, and optional units.
  Optimizers use normalized coordinates; jobs receive denormalized assigned values.
- rawData is one or more schema-versioned `.npz` evidence files. The directory is
  flat: every file is directly under `rawData/` and no subdirectory is valid.
- Cost is the current objective tuple calculated by workspace `calc_cost.py` from
  rawData. Objective names, count, physical meaning, scale, and windows are task
  concerns.
- A job is one candidate evaluation and owns parameters, task inputs, rawData,
  lifecycle metadata, transport artifacts, and diagnostics.
- Recorded data is durable evidence and compact provenance. It is not an optimizer
  cache of permanently authoritative cost values.

The logical pipeline is `normalized variables -> assigned task parameters ->
workflow rawData -> current calc_cost -> objective tuple`.

## Source-of-truth policy

Durable source truth includes raw variables once per individual, flat rawData,
schema metadata, workflow start/end information, job/run/generation identities,
execution diagnostics, and lightweight optimization metadata. Normalized variables,
costs, surrogate predictions, and repeated variable payloads inside each rawData item
are derived or scrubbed. A workflow-written `cost.json` is forbidden.

Changing `calc_cost.py` intentionally changes interpretation of existing compatible
rawData. Changing parameter definitions changes normalization and job static hashes.
If task semantics make old evidence invalid, users must remove or exclude it
explicitly; the package does not guess a scientific migration.

Optimizer and surrogate are consumers of the same evidence. The surrogate predicts
rawData before cost, may train with task-owned importance weights, reconstructs full
public rawData, and calls current cost logic. It never establishes a parallel
`variables -> cost` truth path. Its schedules, state, and checkpoints are keyed by
effective workspace paths.

## Invariants

- Local/distributed evaluators differ only in execution transport.
- Parameter and objective counts come from the currently selected workspace.
- All population-return paths preserve input order and objective width.
- Individual failures yield diagnostic records and infinite costs without deleting
  successful evidence.
- Stored rawData stays rich enough for later cost changes and surrogate learning;
  task cost code may select smaller windows when calculating objectives.
