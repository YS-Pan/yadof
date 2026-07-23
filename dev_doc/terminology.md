# Project-specific terminology

| Term | Meaning |
|---|---|
| `installed package` | The complete `yadof` framework under site-packages: APIs, CLI, defaults, templates, adapters, worker support, tools, and read-only docs. It is not a runtime write location. |
| `agent documentation` | Version-matched task-authoring and question-answering guidance under root `agent_doc/`, exposed from an installed package through `yadof docs`; it replaces the former user-documentation audience. |
| `workspace` | One explicitly selected writable root owning `config.py`, `job_template/`, jobs, records, checkpoints, logs, and tool output. |
| `workspace marker` | Portable `.yadof/workspace.json` provenance published last by init. It never authorizes overwrite, repair, or automatic upgrade. |
| `WorkspaceContext` | Immutable absolute workspace/path value used by stateful public APIs. Relative configured paths resolve from its root. |
| `effective config` | Validated immutable merge of package defaults, workspace uppercase values, and temporary call overrides, in that precedence order. |
| `task module snapshot` | Freshly compiled workspace task and local helpers in a temporary namespace; same-named helpers in two workspaces cannot contaminate each other. |
| `PARAMETERS` | Canonical unassigned `Parameter` objects in workspace `job_template/parameters_constraints.py`; each job receives a fresh assigned snapshot. |
| `expensive evaluation` | A real simulator/custom workflow producing rawData and lifecycle metadata, never authoritative cost. |
| `rawData` | Durable task evidence in schema-versioned direct `rawData/*.npz` files; subdirectories and non-`.npz` entries are invalid. |
| `rawData.zip` | Distributed transport archive created on the execute node and explicitly returned by HTCondor instead of `rawData/`; every member is a direct `.npz` basename with no enclosing directory. |
| `cost` | Current objective tuple dynamically calculated from rawData by workspace `calc_cost.py`. |
| `workspace recorded data` | Workspace-local JSONL/zip evidence and optimization metadata; normalized variables and costs are derived. |
| `package worker support` | The single reserved `worker_misc.py` copied as a direct job-local file; it provides dependency-free workflow helpers and flat zip creation without sending yadof to workers. |
| `self-contained parameter snapshot` | Assigned job-local `parameters_constraints.py` with a minimal local `Parameter` representation and no yadof import. |
| `direct workflow submission` | Windows HTCondor contract in which `workflow.py` itself is `executable` with `transfer_executable=True`; there is no yadof launcher. |
| `job_static_hash` | Definition-oriented hash of task/worker inputs that excludes runtime metadata and per-candidate assignments. |
| `standalone smoke test` | `yadof smoke-test`: exactly one midpoint real task, no generation/per-job/whole-generation timeout; edited tasks require explicit real-task intent. |
| `run smoke` | Optional pre-run real-task smoke chosen by workspace config unless `--smoke-test` or `--no-smoke-test` overrides it. Failure prevents generation submission. |
| `local mode` | Prepared workflow subprocess execution using the installed package and selected workspace. |
| `distributed mode` | HTCondor transport preserving the local job/result/recording contract. |
| `HTCondor runner` | `yadof.evaluate_manager.condor_runner`, which writes submit files, submits/polls/collects, records ClassAds, and diagnoses but never repairs the pool. |
| `slot user` | Low-privilege Windows HTCondor execution account; normal policy is `run_as_owner=False`, `load_profile=True`. |
| `adaptive resource request` | Workspace-history-derived memory/disk request; CPU remains a user policy. |
| `yadof resource retry` | Fresh bounded submission after standard memory/disk holds, doubling only the exhausted request and preserving attempt diagnostics. |
| `adaptive time limit` | Per-normal-job `allowed_execute_duration` derived from smoke/prior generation or fixed config, separate from the submit-side generation deadline. |
| `GPSAF` | Alpha/beta/gamma surrogate-assistance framing implemented by `yadof.optimize` with real-evaluation validation and exploration quota. |
| `surrogate cost interval` | Per-objective min/max across conditional-INR ensemble members after predicted rawData is converted by current cost policy. |
| `staggered surrogate training` | Submit real jobs first, then train at most one workspace-local background model while execution is busy, subject to lag bounds. |
| `packaged adapter` | Read-only reusable resource listed/copied by `yadof task`; active jobs use only the workspace copy. |
| `software task namespace` | The software-identifying CLI level below `yadof task` for non-generic actions, such as `yadof task hfss`; it prevents different adapters from competing for an ambiguous generic action name. |
| `task-specific test` | Test tied to a concrete model/design/objective. It belongs in a disposable/external workspace, not the generic default suite. |
| `user` | Prepares workspace tasks, runs campaigns, and inspects results without maintaining system infrastructure. |
| `administrator` | Installs dependencies and maintains HTCondor/software/hardware; resources live under `admin_tool/`. |
| `manual toDo` | Root `dev_doc/toDo/*.md`; reading supplies context but execution requires an explicit user request. |
| `automatic toDo` | Low-priority `toDo/auto/` handoff considered only when normal in-scope work naturally triggers it and its obsolete rule permits. |
| `change record` | Append-only time-named explanation under `dev_doc/change_records/`; not read by default. |
