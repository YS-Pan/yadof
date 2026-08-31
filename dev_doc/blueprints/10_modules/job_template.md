# Module blueprint: job_template

## Responsibility

`yadof.job_template` is stable framework support for task-owned workspace files. It
defines parameter semantics, current task queries, assigned job snapshots, rawData
schema/views/validation, reusable axis reduction,
definition-based cost dispatch, constraint/failure policy, and objective counting.
It also freezes named rawData templates and projects transient surrogate draws
through one current task interpreter. It does not contain a concrete simulator,
objective, posterior model, or acquisition rule.

## Task-owned files and roots

- `job_template/parameters_constraints.py` defines canonical unassigned `PARAMETERS` and textual
  constraints using packaged `Parameter` on the submit side.
- `job_template/workflow.py` consumes assigned values, controls task-specific simulators/custom
  software, and writes task-specific direct `rawData/*.npz` inside
  `worker_misc.run_workflow()`. Package worker support owns standard paths,
  lifecycle/error metadata, execute-side `execute_machine`, rawData preparation,
  and flat `rawData.zip`. The task file must not duplicate these mechanisms or
  write cost.
- Optional `job_template/evaluation.py` declares fast compatibility through callable
  `evaluate_rawdata(parameters, context)`. It receives a read-only named-value
  mapping and a context without job paths, then returns unique direct `.npz`
  basenames mapped to schema-valid memory payloads plus optional JSON diagnostics.
  A normal `workflow.py` may call the same kernel and serialize those payloads so
  fast/local task algorithms do not drift.
- `submit/calc_cost.py` reports objective names and contains task-specific rawData
  interpretation, objective definitions, thresholds, and calculators. It cannot
  select or weight surrogate training positions; validation rejects the removed
  `rawdata_importance_weights()` hook. The file calls package helpers for reusable
  loading/reduction/dispatch, constraints, failure fallback, and objective counting.
- `submit/optimization.py` either declares the explicit v1
  `optimization_program(context)` entry plus exact program helpers, or temporarily
  defines the transitional side-effect-free `build_optimization()` composition.
  Explicit program control flow is frozen once per run; current cost and other task
  sources remain generation-scoped. Submit helpers stay submit-side.
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

One rawData field represents one coherent semantic quantity. Independent scalars or
curves remain independent fields even when they share a coordinate grid; task code
does not concatenate unrelated 1-D curves behind an invented channel dimension.
A multidimensional field is appropriate only when its axes jointly define one
physical grid/tensor that the prediction contract intends to model as such.

For derived posterior samples, `RawDataSchemaTemplate` freezes the exact canonical
selector `(direct .npz basename including .npz, resolved values/data main key)` for
each field. Its signature includes the selector set, main shape/dtype
representation, and every non-main template value such as axes, unit scalars, and
metadata, but excludes the predicted main values. Reconstruction requires exactly
that selector set and produces a complete `StructuredRawDataSample`; validation
rejects missing/extra fields and schema drift instead of padding or guessing.

## Cost contract

Costs are recomputed through freshly loaded current `submit/calc_cost.py`. A long-running
cost-history view instead opens one explicit package-owned interpreter context,
freezing parameter definitions and `calc_cost.py` for all of its batches. Returned rows
must match reported objective width and contain only finite numeric values. Both
point-in-time calculation and frozen `CostInterpreter` apply this same callback,
width, and finite-value contract. The same path is used for completed simulation
evidence, history queries, and surrogate-predicted rawData. Raw variables may be
supplied when a task needs them, but rawData remains the evidence source.
`get_objective_count()` is package-derived from validated objective names; task
modules do not repeat that calculation.

Fresh loading is also the campaign hot-change boundary. One generation selects one
coherent task snapshot. The next generation may observe changed parameter
ranges/levels, fixed-width objective names/definitions, cost code,
workflow/evaluation code, and local task helpers. Parameter identity/count and
objective count remain stable in the current hot-change contract; add/remove/rename
or objective-width changes are future work. Stored raw variables and rawData are
reinterpreted through the current snapshot when mechanically possible. Task/source
signatures may invalidate derived caches and record provenance, but job_template
does not use them to judge scientific equivalence or automatically reject old
evidence.

`RawDataCostProjector` is a thin adapter around an injected frozen
`CostInterpreter`. It denormalizes each matching candidate with the interpreter's
frozen parameters, validates a complete structured sample against the frozen
template, invokes the same `calc_cost.py` callback, and checks objective width and
finite results. It projects each draw/candidate independently into
`[draw,candidate,objective]` plus a validity mask and bounded typed diagnostics;
invalid costs remain `NaN`. A finite callback result such as task-level
`error_cost=1.0` is valid because callback fallback provenance is intentionally not
part of `CostInterpreter`. Schema, callback, width, and non-finite failures are
invalid. The context-managed `task_rawdata_cost_projector()` keeps the callback
loaded for the complete projection and uses the generation snapshot when that
snapshot workspace is supplied.

New task objectives are independently normalized dimensionless minimization costs
in `[0, 1]`. `soft_cost()` is the canonical fixed-`p=2` algebraic mapping from
task-owned physical `goal`/`worst` thresholds; registered task-cost calculators use
that mapping, and custom rawData callbacks call it explicitly. Task fallback uses
`error_cost=1.0`. Physical units remain in rawData/extraction code, and observed
history or population extrema never define the scale. Framework execution-failure
rows may remain all-`inf` as a separate isolation sentinel.

The default `edge_cost=0.1` makes `goal`/`worst` calibration anchors at `0.1`/`0.9`
rather than clipping bounds at `0`/`1`. The slow outer algebraic tails preserve
ordering when conservative thresholds are exceeded; task code must not pre-clip
physical values or linearly rescale away those tails.

For centered position `x = (value - goal) / (worst - goal) - 0.5`, calculate
`0.5 * (1 + a*x / sqrt(1 + (a*x)**2))`. Derive the default scale as
`a = (1 - 2*edge_cost) / sqrt(edge_cost * (1 - edge_cost))`, which gives `a=8/3`
for the default anchors. Use a stable `p=2` denominator such as `hypot(1, a*x)` so
very large finite physical values remain bounded instead of overflowing.

## Invariants

- Task modules are workspace-explicit and fresh-loaded.
- A campaign does not freeze cost, parameter, workflow, evaluation, or other task
  sources selected at startup; supported edits become coherent at the next
  generation boundary. Explicit optimization program sources are the deliberate
  run-scoped exception.
- Workflows do not import yadof in distributed execution.
- Workflows call copied package worker support, which samples `execute_machine` on
  the node where they run and includes it in returned individual metadata.
- Rich rawData is preserved; cost code may select objective-relevant windows.
- Identical rawData has the same fixed-threshold normalized cost regardless of the
  other samples currently recorded or evaluated.
- Current-cost callbacks are deterministic and replayable: they do not mutate
  evidence or depend on one-shot external side effects, because process loss may
  cause committed evidence to be interpreted again.
- `cost.json` is never an authoritative task output.
- Fast task kernels return rawData rather than cost and are rejected explicitly when
  missing or malformed; there is no fallback to local workflow emulation.
- Code invariant across optimization tasks lives in yadof; code that changes with
  the task lives in `job_template/workflow.py` or `submit/calc_cost.py`.
- Prepared jobs never contain `submit/` sources and receive a generated assigned
  parameter snapshot instead of the canonical source.
- A yadof helper must be a stable contract or a mechanism reasonably reusable
  across different task families. One-off array layouts, specialized grouping, and
  narrow objective rules remain task-owned rather than becoming package APIs.
- Named posterior samples and projected objectives are transient; job_template
  projector code never imports surrogate backends, calls the recorder, or changes
  worker/rawData/recorded-data formats.
