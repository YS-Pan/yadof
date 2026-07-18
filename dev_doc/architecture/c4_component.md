# C4 package components

- `workspace`, `workspace_manifest`, `workspace_init`, `workspace_check`: resolve,
  create, and diagnose user-owned workspaces without implicit package writes.
- `config`: immutable effective values with package < workspace < temporary override
  precedence and validation.
- `task_loader`, `job_template`: fresh isolated task loading, parameter assignment,
  normalization, rawData schema, and current cost policy.
- `evaluate_manager`: job preparation, local subprocesses, HTCondor submit/collect,
  resource calibration/retry, execution limits, worker compatibility bootstrap, and
  recording handoff.
- `recorded_data`: workspace-local JSONL/zip evidence, locks, diagnostics, and
  dynamically interpreted history.
- `optimize`: pymoo GA/NSGA-III mechanics, GPSAF pressure, warm start, generation
  metadata, start/resume, and optional strict all-infinite failure.
- `surrogate`: workspace-keyed schedules/state, conditional INR deep ensemble,
  rawData prediction, dynamic cost conversion, audits, and recoverable checkpoints.
- `tools`, `resources`: view/history/task utilities and read-only adapter/template/doc
  resources.
- `cli`, `run_command`: installed command routing and normal campaign orchestration.

Stable cross-module calls use public `api.py` or package `__init__` exports. Stateful
APIs accept a workspace; no module derives user-data paths from package `__file__`.
