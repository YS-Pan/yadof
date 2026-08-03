# Module blueprint: job_template

## Responsibility

`yadof.job_template` is stable framework support for task-owned workspace files. It
defines parameter semantics, current task queries, assigned job snapshots, rawData
schema/views/validation, reusable axis reduction and importance allocation,
definition-based cost dispatch, constraint/failure policy, and objective counting.
It does not contain a concrete simulator or objective.

## Task-owned files

- `parameters_constraints.py` defines canonical unassigned `PARAMETERS` and textual
  constraints using packaged `Parameter` on the submit side.
- `workflow.py` consumes assigned values, controls task-specific simulators/custom
  software, and writes task-specific direct `rawData/*.npz` inside
  `worker_misc.run_workflow()`. Package worker support owns standard paths,
  lifecycle/error metadata, execute-side `execute_machine`, rawData preparation,
  and flat `rawData.zip`. The task file must not duplicate these mechanisms or
  write cost.
- Optional `evaluation.py` declares fast compatibility through callable
  `evaluate_rawdata(parameters, context)`. It receives a read-only named-value
  mapping and a context without job paths, then returns unique direct `.npz`
  basenames mapped to schema-valid memory payloads plus optional JSON diagnostics.
  A normal `workflow.py` may call the same kernel and serialize those payloads so
  fast/local task algorithms do not drift.
- `calc_cost.py` reports objective names and contains task-specific rawData
  interpretation, objective definitions, thresholds, calculators, and importance
  regions. Importance regions assign relative attention to already modeled rawData;
  they do not select saved evidence or surrogate inclusion. The file calls package
  helpers for reusable loading/reduction/dispatch, constraints, failure fallback,
  weight allocation, and objective counting.
- adapters, models, lookup data, and task helpers are copied into prepared jobs when
  placed under `job_template/`.

## Parameter handoff

Canonical definitions are fresh-loaded for every assignment. `assign_parameters()`
validates normalized values and denormalizes through ranges/levels in memory.
Prepared-job materialization adapts that same assigned snapshot and writes it atomically as a
self-contained `parameters_constraints.py` in the job. The assigned snapshot has a
small local `Parameter` representation and imports no yadof, so execute nodes do not
receive the package. Static hashing interprets that representation through fields,
not class identity.

## rawData contract

Each `.npz` contains numeric values plus JSON metadata with current schema version
and exact shape; axis names/values and task metadata are supported. A rawData output
directory is flat and contains only direct `.npz` files. Validation rejects nested
directories, unsupported files, missing/legacy metadata, nonnumeric arrays, shape or
axis mismatches, and invalid item structures.

## Cost contract

Costs are recomputed through freshly loaded current `calc_cost.py`. Returned rows
must match reported objective width. The same path is used for completed simulation
evidence, history queries, and surrogate-predicted rawData. Raw variables may be
supplied when a task needs them, but rawData remains the evidence source.
`get_objective_count()` is package-derived from validated objective names; task
modules do not repeat that calculation.

New task objectives are independently normalized dimensionless minimization costs
in `[0, 1]`. `soft_cost()` is the canonical tanh mapping from fixed task-owned
physical `goal`/`worst` thresholds; registered task-cost calculators use that
mapping, and custom rawData callbacks call it explicitly. Task fallback uses
`error_cost=1.0`. Physical units remain in rawData/extraction code, and observed
history or population extrema never define the scale. Framework execution-failure
rows may remain all-`inf` as a separate isolation sentinel.

The default `edge_cost=0.1` makes `goal`/`worst` calibration anchors at `0.1`/`0.9`
rather than clipping bounds at `0`/`1`. The outer tanh tails preserve ordering when
conservative thresholds are exceeded; task code must not pre-clip physical values
or linearly rescale away those tails.

## Invariants

- Task modules are workspace-explicit and fresh-loaded.
- Workflows do not import yadof in distributed execution.
- Workflows call copied package worker support, which samples `execute_machine` on
  the node where they run and includes it in returned individual metadata.
- Rich rawData is preserved; cost code may select objective-relevant windows.
- Identical rawData has the same fixed-threshold normalized cost regardless of the
  other samples currently recorded or evaluated.
- `cost.json` is never an authoritative task output.
- Fast task kernels return rawData rather than cost and are rejected explicitly when
  missing or malformed; there is no fallback to local workflow emulation.
- Code invariant across optimization tasks lives in yadof; code that changes with
  the task lives in `workflow.py`/`calc_cost.py`.
- A yadof helper must be a stable contract or a mechanism reasonably reusable
  across different task families. One-off array layouts, specialized grouping, and
  narrow objective rules remain task-owned rather than becoming package APIs.
