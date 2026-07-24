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
- `_resources`: generic workspace template, reusable adapter references, minimal
  worker helper, and installed documentation resources.

## Task interpretation

- `job_template.api`: current parameter/objective queries, assignment
  materialization, normalization, dynamic cost, importance weights, and task
  validation.
- `parameters_constraints_class`: canonical submit-side `Parameter` semantics.
- `rawdata_contract`: schema-versioned `.npz` validation and rawData views.
- `cost_misc`: neutral multi-sample cost calculation helpers.

## Evaluation

- `evaluate_manager.api`: backend selection, population ordering, local worker pool,
  per-individual failure isolation, recording, and cost return.
- `job_files`: task copying, self-contained assigned parameter snapshots, job static
  hashes, package worker-helper copying, and preparation provenance.
- `local_runner`: direct workflow subprocess, timeout/process cleanup, rawData
  validation, and shared metadata finalization.
- `condor_runner`: direct `workflow.py` submit, input selection, explicit
  `rawData.zip` transport, flat archive restoration, queue polling, collection,
  `condor.log` execution-clock watchdog, bounded removal, ClassAd diagnostics, and
  pool matchmaking analysis.
- `resource_requests`, `resource_retries`, `time_limits`: workspace-local adaptive
  policy separated from backend orchestration.
- `job_result`, `types`: common result shape and metadata utilities.
- `recorded_data_client`: narrow evaluation-to-persistence boundary.

## Durable evidence and optimization
- `recorded_data`: workspace-local JSONL/zip evidence, locks, atomic generation-
  batch recording, diagnostics, and dynamically interpreted history.
- `optimize`: pymoo GA/NSGA-III mechanics, GPSAF pressure, warm start, generation
  metadata, start/resume, and optional strict all-infinite failure.
- `surrogate`: workspace-keyed schedules/state, conditional INR deep ensemble,
  rawData prediction, dynamic cost conversion, audits, and recoverable checkpoints.
- `tools`, `_resources`: view/history/task utilities and read-only adapter/template/doc
  resources. Software-specific task commands live below an explicit software
  namespace, such as `yadof task hfss`, so future adapters do not collide on generic
  action names.
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
