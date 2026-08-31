# Migrating a yadof 0.4.2 workspace to 0.5.0

yadof 0.5.0 makes the explicit workspace optimization program mandatory. This is a
breaking cutover: there is no compatibility switch, warning-only alias, or automatic
translation for a 0.4.2 `build_optimization()` file. Migrate and validate the task
at a complete generation boundary before starting a 0.5.0 run.

## Replace the optimization entry

`submit/optimization.py` must contain a literal `YADOF_OPTIMIZATION_PROGRAM`
declaration with exactly `api`, `entry`, `helpers`, `identity`, and `capabilities`.
The declared synchronous entry receives one framework-created context, opens one
run scope, processes each bounded generation in order, and commits exactly one real
result per generation.

Use `yadof init` in a scratch directory to inspect the current conservative starter.
For an existing task, replace only its old optimization composition; preserve its
task-owned config, parameter definitions, workflow, rawData, and cost code. A normal
program explicitly performs these operations:

1. materialize any evidence/cost view needed by selection or training;
2. select a population with `full_real_search()`, `select_gpsaf_generation()`, or
   `PosteriorAssistedSelector.select_generation()`;
3. call `start_evaluation(step.prepare_evaluation(population))`;
4. explicitly start/join any independent surrogate training;
5. wait and close the evaluation handle; and
6. commit one `step.result(...)` containing authoritative real costs.

The `helpers` tuple is a literal, ordered closure of relative `.py` files below
`submit/`. yadof freezes `optimization.py` and those exact helpers once per command.
`yadof check` parses their static top-level shape without importing or executing
arbitrary program code.

## Removed orchestration APIs

The following 0.4.2 surfaces do not exist in 0.5.0:

| Removed surface | 0.5.0 replacement |
| --- | --- |
| `build_optimization()` | literal program declaration and entry |
| `OptimizationStrategy`, `OptimizationDefinition`, `load_workspace_strategy()` | program/run/generation scopes and retained value types |
| `gpsaf()` / `GPSAFStrategy` | `gpsaf_settings()` plus `select_gpsaf_generation()` |
| `real_search()` / `RealSearchStrategy` | `full_real_search()` |
| `posterior_assisted()` / `PosteriorAssistedStrategy` | `posterior_assisted_selector()` / `PosteriorAssistedSelector` |
| strategy-owned `run_generation()` and evaluation/training/commit loops | explicit program operations |
| evaluation `after_jobs_submitted` callback | start an evaluation handle, then start independent work |
| component-internal session reads for training/posterior data | explicit `SurrogateTrainingData` arguments |

`evaluate_manager.evaluate_population()` remains as an independent synchronous
convenience API, but it accepts no submission callback. Program code normally uses
the handle form so ownership and overlap are visible.

## Settings and scientific behavior

Search, surrogate, qNEHVI, and GPSAF parameters remain component-owned Python
arguments. GPSAF `alpha`, `beta`, `gamma`, and `exploration_fraction` are retained;
`gamma` is neither removed nor deprecated. Moving the orchestration into the
workspace must not silently change seeds, archive/duplicate rules, objectives, or
the meaning of a training-data transform.

The current conditional-INR and hierarchical-CAE posterior capabilities remain
typed but scientifically blocked for qNEHVI exploitation. A
`PosteriorAssistedSelector` fails closed to full-real selection while performance,
calibration, transferability, or applicability requirements are unresolved. Do not
edit readiness diagnostics to force entry.

## State, checkpoints, and resume

Program identity, capabilities, component settings, parameter/objective names, and
the frozen source fingerprint contribute to run/state identity. Keep the literal
identity stable only while semantics are unchanged. A changed program begins under
the appropriate new identity/namespace rather than reinterpreting an incompatible
checkpoint.

Recorded real evidence remains workspace evidence, subject to the task's normal
history policy. Surrogate reuse additionally requires matching component identity,
training content/provenance, task interpretation, and freshness contracts. There is
no automatic 0.4.2 strategy-state or checkpoint conversion; incompatible state is
not silently adopted.

A 0.5.0 resume must start at the exact next incomplete generation for the same
program signature. Program and helper sources remain frozen for one command. Make
coherent task edits only between commands at a complete-generation boundary; an
incomplete old orchestration run must be resolved or restarted deliberately.

## Starter, examples, and benchmark package

The sole `yadof init` starter is a complete explicit conditional-INR + GPSAF
program. It is a conservative reference, not a selector registry. The source
checkout also provides the five copyable programs listed in
[optimization_program_examples.md](optimization_program_examples.md), including
real-only, sequential and overlapped training, an explicit data split, and honest
posterior fallback.

The independently versioned benchmark runner cuts over at yadof-benchmark 0.3.0 and
requires yadof 0.5.0 or newer. Benchmark strategy cells accept only the same literal
program declaration and declared helper closure as ordinary workspaces.

## Acceptance checklist

- Back up or commit the user-owned workspace and stop all active campaigns.
- Migrate `submit/optimization.py`; update any custom imports to the new names.
- Run `yadof check --workspace PATH` and resolve every static program error.
- Run a small fast/local smoke only when the task's execution risk permits it.
- Confirm one generation records the expected program signature, source fingerprint,
  real population/cost count, and explicit training/fallback diagnostics.
- Resume a larger campaign only from a verified complete boundary.

yadof 0.5.0 intentionally does not accept both old and new paths. A rejection that
mentions the removed 0.4.x entry means the workspace has not yet been migrated.
