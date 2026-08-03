# 4+1 logical view

## Domain concepts

- Parameter definitions contain names, allowed ranges/levels, and optional units.
  Optimizers use normalized coordinates; jobs receive denormalized assigned values.
- rawData is one or more schema-versioned `.npz` evidence files. The directory is
  flat: every file is directly under `rawData/` and no subdirectory is valid.
- Cost is the current objective tuple calculated by workspace `calc_cost.py` from
  rawData. Newly authored task objectives are independent, dimensionless
  minimization costs in `[0, 1]`, with fixed task-owned physical `goal`/`worst`
  thresholds and `1.0` as the task-level error fallback. Objective names, count,
  physical meaning, thresholds, and windows are task concerns; physical units stay
  in rawData and extraction logic. Framework execution failures may still use an
  all-`inf` sentinel outside the normal task-cost scale.
- A prepared job is one local/distributed candidate evaluation and owns parameters,
  task inputs, rawData, lifecycle metadata, transport artifacts, and diagnostics.
  A fast logical evaluation keeps the identity/metadata contract but has no durable
  job directory; its evidence is memory-backed until recorded.
- Recorded data is durable evidence and compact provenance. It is not an optimizer
  cache of permanently authoritative cost values.

The logical pipeline is `normalized variables -> assigned task parameters ->
workflow rawData -> current calc_cost -> objective tuple`.

`workflow.py` and `calc_cost.py` own only the task-variable parts of that pipeline.
The package owns invariant execution lifecycle, paths, metadata, transport,
rawData manipulation, cost dispatch, constraint/failure policy, and objective
counting. Task files select and parameterize those package mechanisms.

Resource evidence follows a parallel backend-neutral interpretation path. Local
process-tree measurements and HTCondor ClassAd measurements publish common CPU,
memory, and disk keys. One shared calibration component selects smoke or
preceding-generation evidence and trims its upper tail. HTCondor turns the result
into scheduler requests; local mode turns it into a safe worker count constrained
by current submit-host capacity.

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
rawData before cost, constructs its modeled query table from compatible recorded
numeric rawData, reconstructs full public rawData, and calls current cost logic.
Task-owned importance weights change full-query loss attention or stochastic query-sampling
probability within that query table; they never select which rawData is saved or
added to the surrogate. It never establishes a parallel `variables -> cost` truth
path. Its schedules, state, and checkpoints are keyed by effective workspace paths.

## Invariants

- Fast/local/distributed evaluators differ in execution transport and intermediate
  evidence backing, but converge before durable recording and current cost.
- Fast uses bounded reusable local processes. A crash or timeout discards and
  replaces only that worker, cleans its configured scratch, and preserves ordering.
- Local concurrency is bounded by population size, an explicit cap, physical CPU,
  currently available memory, and free disk; smoke remains exactly one worker.
- Parameter and objective counts come from the currently selected workspace.
- All population-return paths preserve input order and objective width.
- Individual failures yield diagnostic records and infinite costs without deleting
  successful evidence.
- Stored rawData stays rich enough for later cost changes and surrogate learning;
  task cost code may select smaller windows when calculating objectives.
- New task cost policies use fixed physical thresholds and a bounded mapping rather
  than history/population-dependent normalization, so identical evidence retains
  the same interpretation independently of other samples.
- No task module duplicates behavior that is invariant across optimization tasks,
  and no package module hard-codes behavior that changes with a task.
