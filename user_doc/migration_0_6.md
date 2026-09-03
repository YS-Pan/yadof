# Migrating fast workspaces to resident sessions

Release 0.6 also changes `gpsaf_settings()` to greedy-HV infill selection. Shipped
programs state `infill_selection="hypervolume"` explicitly. Set
`infill_selection="cluster"` to preserve PKT/gamma batch selection; alpha, beta,
error estimation, genetic operators and exploration retain their contracts. See
[GPSAF mechanisms](gpsaf.md) for marginal-gain selection and fallback ordering.

The `fast` mode now requires `YADOF_FAST_API = "yadof.fast.session/v1"` and
`create_evaluation_session(context)` in `job_template/evaluation.py`. A module-level
`evaluate_rawdata(parameters, context)` alone is no longer accepted. `yadof check`
validates the declaration without constructing a session or starting a simulator.
There is no legacy execution fallback.

The factory returns an object with `evaluate_rawdata(parameters, context)` and
`close()` methods. Move the existing physical calculation into the method. Return
the same complete named rawData mapping and optional JSON diagnostics; never return
costs. Keep one physical kernel for fast and prepared local/distributed workflows.
The prepared wrapper creates one session, evaluates once, writes the payloads to
`rawData/`, and closes in `finally`. The default template demonstrates this pattern.

The factory receives a read-only context with `session_dir`, `environment`,
`timeout_sec`, and `task_static_signature`. Session resources may retain imported
modules, immutable model data and an eligible external interpreter. They must stay
below the supplied session directory. The evaluation method receives a separate
read-only candidate context: `evaluation_name`, `scratch_dir`, `environment`,
`timeout_sec`, `run_id`, `optimization_index`, `generation_index`, `population_index`,
and `task_static_signature`. Parameters are a read-only assigned name/value mapping.

Every call must reconstruct or reliably reset its physical state. Reusing a process
does not authorize a numerical warm start, cached result, retained candidate arrays,
or dependence on candidate order. Release per-candidate solver objects and temporary
files before returning. `close()` releases session resources and must tolerate
cleanup after errors. A factory that fails part way through construction owns
cleanup of anything it allocated before raising.

One campaign owns each bounded worker pool. Compatible workers and their loaded
task modules survive generation boundaries; standalone evaluation closes its pool
before returning. A task/model/adapter/parameter or simulation-config change closes
affected sessions at the next generation boundary. Environment, worker-cap, or
timeout changes also replace the pool before evaluation. A cost-only source change
preserves compatible simulation sessions while current costs are recalculated.
Generation handles must still finish and close before advancing.

Optional `PHYSICAL_FAILURE_TYPES` is a tuple of specific exception types, excluding
`Exception` and `BaseException`. A declared physical failure records a failed formal
attempt but may reuse the session for a subsequent candidate. Other task exceptions
replace the worker. Timeout, crash and cancellation terminate the worker tree;
normal closure first calls the task's `close()` and then reaps remaining descendants.
Session cleanup failures are visible. Long-lived tasks must bound caches and child
process counts. Framework stdout/stderr capture keeps an 8,000-character tail.

Fast still validates complete rawData, applies normal recorder backpressure, waits
for durable receipts, and interprets current costs. Recorded evidence remains
available for cost recalculation, training, recovery and registered postprocessors.
Session and candidate scratch are temporary, not history or a resume mechanism.

For Chrono, update the copied `chrono_com.py` and use `PyChronoSession` with a
`resident_worker_main(simulate)` child, where `simulate(request)` returns memory
rawData and diagnostics. The bounded `yadof.pychrono-session/v1` transport uses JSON
descriptors and numeric array bytes, never pickle. It carries up to 64 MiB of arrays
per result and bounds request/descriptor and diagnostic storage. Each request gets
fresh child scratch. Rebuild the Chrono system each time, including required
deterministic system initialization. A handled physical error can continue; a timed
out or crashed external process is closed and subsequently replaced.

Ngspice may continue one batch process per candidate. `rawdata_payload()` constructs
the same exported arrays in memory and can reuse a parsed `NgspicePlot`; solver
internal netlist/rawfile I/O remains. A session interface does not imply every
simulator supports resident solving.

Initialize fresh benchmark workspaces with `yadof-benchmark>=0.6,<0.7` and
`yadof>=0.6,<0.7`. Existing benchmark run inputs and evidence are immutable; do not
replace their adapters in place. Upgrading a task does not authorize another
execution of an already-used benchmark workspace.
