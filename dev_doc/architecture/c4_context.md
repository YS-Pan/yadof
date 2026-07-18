# C4 Context

## Scope
`yadof` is a local-first optimization framework for expensive simulation workflows. It coordinates optimization, job execution, rawData persistence, surrogate training, and optional user tools.

The current distribution transition has an installable `yadof` foundation for
version/help/document resources plus explicit workspace, effective-config, and
isolated task-loading APIs. The optimization runtime remains under `project/` for
later staged migration.

## Context Diagram

```mermaid
flowchart LR
    User["User / researcher"] -->|edits task files and config| Yadof["yadof project"]
    User -->|launches tests, optimization, tools| Yadof
    Administrator["Administrator"] -->|installs and maintains| Environment["Python, dependencies, HTCondor pool"]
    Environment --> Yadof
    Yadof -->|runs workflow locally| Python["Local Python runtime"]
    Yadof -->|optional distributed jobs| HTCondor["HTCondor cluster"]
    Yadof -->|future real simulations| Simulator["Simulator adapters: HFSS, Maxwell, TwinBuilder, custom Python"]
    Yadof -->|reads/writes| FS["Workspace filesystem: jobs, recorded_data, surrogate checkpoints"]
    Tools["Optional plotting / maintenance tools"] -->|public APIs| Yadof
```

## External Actors
- User: prepares task definitions, decides when old history is still valid, launches runs, and inspects results. A user does not configure or maintain the system environment.
- Administrator: installs yadof and dependencies, and configures and maintains HTCondor cluster software and hardware. Administrator actions are outside the normal campaign workflow.
- Local Python runtime: executes the current `workflow.py` in isolated job folders.
- Simulator adapters: future or optional adapters that turn variables into rawData.
- HTCondor: optional distributed backend used by `evaluate_manager` when `EVALUATION_MODE = "distributed"`.
- Filesystem: the durable persistence layer for source files, job folders, individual metadata, optimization metadata, archived rawData, and surrogate checkpoints.

## System Responsibilities
- Publish one `yadof` distribution/command/import name with a single version source
  and read-only packaged documentation/template resources.
- Resolve one selected writable workspace into explicit absolute config, task,
  jobs, record, checkpoint, log, and tool-output paths.
- Merge and validate package defaults, workspace config, and temporary overrides;
  freshly load task modules without cross-workspace import contamination.
- Generate candidate populations in normalized variable space.
- Convert normalized candidates into task-specific raw variables.
- Run a workflow that produces rawData only.
- Persist raw variables, rawData, and metadata.
- Calculate cost dynamically from rawData.
- Train and use surrogate models without bypassing rawData.

## Out Of Scope
- Binding the core framework to one simulator.
- Persisting `cost.json` as an authoritative result.
- Requiring HTCondor or a real simulator for default tests.
