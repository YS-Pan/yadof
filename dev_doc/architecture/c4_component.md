# C4 package components

## Foundation

- `workspace.context`, `workspace.manifest`, `workspace.init`, `workspace.check`:
  resolve, create, and diagnose user-owned workspaces without implicit package
  writes.
- `config`: immutable effective values with package < workspace < temporary override
  precedence and validation.
- `task_loader`: fresh compile/execute in temporary module namespaces, including
  workspace-local helper packages without lasting `sys.path` or `sys.modules`
  pollution.
- `_resources`: generic workspace template, reusable adapter references, invariant
  execute-side worker lifecycle support, and installed documentation resources.

## Task interpretation

- `job_template.api`: current parameter/objective queries, assignment
  materialization, normalization, dynamic cost, importance weights, and task
  validation.
- `parameters_constraints_class`: canonical submit-side `Parameter` semantics.
- `rawdata_contract`: schema-versioned `.npz` validation, rawData views, reusable
  axis-curve reduction, and importance-weight allocation.
- `cost_misc`: neutral multi-sample/defined/custom-callback cost calculation,
  tanh-based physical-to-`[0, 1]` objective mapping, result-width validation,
  worst-curve aggregation, objective-name derivation, constraint handling, and
  failure fallback.

## Evaluation

- `evaluate_manager.api`: backend selection, population ordering, local worker pool,
  per-individual failure isolation, recording, and cost return.
- `fast_runner`, `fast_resources`, `process_control`: reusable spawn workers,
  memory-backed task-kernel execution, bounded host-capacity concurrency, ephemeral
  scratch, hard timeout/crash replacement, and shared process-tree termination.
- `job_files`: task copying, self-contained assigned parameter snapshots, job static
  hashes, package worker-lifecycle copying, top-level AEDT runtime-artifact
  exclusion, and preparation provenance.
- `local_runner`: direct workflow subprocess, timeout/process cleanup, rawData
  validation, psutil process-tree resource measurement, and shared metadata
  finalization.
- `resource_calibration`: backend-neutral smoke/preceding-generation observation
  selection, upper-tail trimming, bootstrap scaling, and concrete per-job estimates
  shared by local and HTCondor policy.
- `local_resources`: submit-host CPU/memory/disk discovery, adaptive worker-count
  planning, process-tree monitoring, and job-directory disk measurement.
- `condor_runner`: direct `workflow.py` submit, input selection, explicit
  `rawData.zip` transport, flat archive restoration, queue polling, collection,
  `condor.log` execution-clock and execute-site parsing, source-labeled timeout
  machine fallback, bounded removal, ClassAd diagnostics, and pool matchmaking
  analysis.
- `resource_requests`, `resource_retries`, `time_limits`: workspace-local adaptive
  policy separated from backend orchestration. Resource requests format
  HTCondor-specific values over the shared calibration result; retry and time-limit
  policies remain backend-specific.
- `job_result`, `types`: common result shape and metadata utilities, including
  explicit file-backed or memory-backed rawData and an optional real job path.
- `recorded_data_client`: narrow evaluation-to-persistence boundary.

## Durable evidence and optimization
- `recorded_data`: workspace-local JSONL/zip evidence, file or named-memory source
  normalization, no-pickle NPZ encoding, locks, atomic generation-batch recording,
  diagnostics, and dynamically interpreted history.
- `optimize`: pymoo GA/NSGA-III mechanics, GPSAF pressure, warm start, generation
  metadata, start/resume, and optional strict all-infinite failure.
- `surrogate`: workspace-keyed schedules/state, conditional INR deep ensemble,
  rawData prediction, dynamic cost conversion, audits, and recoverable checkpoints.
- `tools`, `_resources`: cost view; integrated time/failure/machine/error view;
  grouped `view all` orchestration; history/task utilities; and read-only
  adapter/template/doc resources. The cost view isolates and reports unusable
  history rows, omits unavailable optional annotations, and continues whenever at
  least one finite, consistent objective row remains. `tools.surrogate_viewer` is a lazy, optional
  inspection leaf for GUI prediction, real-result comparison, metadata reports,
  and GUI/terminal cross-generation error audits; its backend owns yadof
  checkpoint/rawData adaptation while its UI and reporting layer never write
  workspace data. The time view colors points by execute-side machine
  metadata and uses directly labeled horizontal bands plus marker rings for error
  types. Software-specific task commands live below an explicit software namespace,
  such as `yadof task hfss`, so future adapters do not collide on generic action
  names.
  The `chrono_com.py` adapter resource owns the isolated Project Chrono
  JSON/NPZ launch/validation boundary; task-owned `chrono_worker.py` owns mechanics.
- `cli`, `run_command`: modular installed command routing, packaged-document access,
  and normal campaign orchestration.

## Dependency direction

`optimize` consumes public evaluation, history, task, and surrogate APIs.
`evaluate_manager` consumes task and recorded-data APIs. `recorded_data` and
`surrogate` may ask `job_template` to reinterpret evidence. Core runtime modules
never import `tools`. Workspace workflows may import files copied beside them and
external installed dependencies, but distributed workflows must not import yadof.

Stable cross-module calls use public `api.py` or package `__init__` exports. Stateful
APIs accept a workspace; no module derives user-data paths from package `__file__`.
Task workflow/cost modules contain task-variable callbacks and definitions only:
they invoke copied `worker_misc` or installed `yadof.job_template` helpers for
invariant behavior. The viewer's package-internal checkpoint/rawData dependencies
remain isolated below its backend and never leak into UI modules or core runtime.
