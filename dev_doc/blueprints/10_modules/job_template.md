# Module blueprint: job_template

## Responsibility

`yadof.job_template` is stable framework support for task-owned workspace files. It
defines parameter semantics, current task queries, assigned job snapshots, rawData
schema/views/validation, cost helpers, and optional rawData importance weights. It
does not contain a concrete simulator or objective.

## Task-owned files

- `parameters_constraints.py` defines canonical unassigned `PARAMETERS` and textual
  constraints using packaged `Parameter` on the submit side.
- `workflow.py` consumes assigned values, controls simulators/custom software, writes
  lifecycle metadata, writes direct `rawData/*.npz`, and creates flat
  `rawData.zip` for distributed return. It must not write cost.
- `calc_cost.py` reports objective names/count and calculates current costs from
  rawData; it may expose importance weights for surrogate training.
- adapters, models, lookup data, and task helpers are copied into prepared jobs when
  placed under `job_template/`.

## Parameter handoff

Canonical definitions are fresh-loaded for every preparation. Normalized values are
validated, denormalized through ranges/levels, and written atomically as a
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

## Invariants

- Task modules are workspace-explicit and fresh-loaded.
- Workflows do not import yadof in distributed execution.
- Rich rawData is preserved; cost code may select objective-relevant windows.
- `cost.json` is never an authoritative task output.
