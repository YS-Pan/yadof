# C4 Component

## Package And Workspace Foundation Components

```mermaid
flowchart LR
    Metadata["pyproject.toml"] --> Console["yadof console script"]
    Version["_version.py"] --> Public["yadof.__version__"]
    Version --> Console
    Console --> Resources["resources.py"]
    RootDocs["root dev_doc + user_doc"] -->|build-time mapping| Resources
    Templates["_resources/templates"] --> Resources
    Templates --> Init["workspace_init.py"]
    Workspace["workspace.py"] --> Config["config.py"]
    Config --> TaskLoader["task_loader.py"]
    Workspace --> JobTemplate["yadof/job_template"]
    TaskLoader --> JobTemplate
    Marker["workspace_manifest.py"] --> Init
    Init --> Config
    Init --> TaskLoader
    Check["workspace_check.py"] --> Marker
    Check --> Config
    Check --> TaskLoader
    Console --> Init
    Console --> Check
    Console --> Smoke["smoke_test.py + yadof smoke-test"]
    Smoke --> PackagedEvaluate["yadof.evaluate_manager"]
    PackagedEvaluate --> Config
    PackagedEvaluate --> JobTemplate
    PackagedEvaluate --> WorkspaceJobs["workspace/jobs"]
```

- `pyproject.toml`: PEP 517 backend, distribution metadata, dependency layers,
  package selection, resource mapping, and the `yadof` console entry point.
- `_version.py`: single literal runtime/distribution version source.
- `cli.py` and `__main__.py`: standard-library argument dispatch for help, version,
  non-GUI document output, init, check, and local smoke with consistent
  streams/status. Runtime-dependent modules remain lazy imports so
  help/version/docs work without extras.
- `resources.py`: `importlib.resources` lookup of installed read-only content plus a
  checkout-only fallback to the same authoritative root docs.
- `workspace.py`: immutable absolute paths for config, task inputs, jobs, recorded
  data, surrogate checkpoints, logs, and tool output. Construction never creates
  directories.
- `config.py`: immutable package defaults, isolated workspace `config.py` execution,
  unknown-name/type/mode/path validation, precedence tracking, and non-mutating
  temporary overrides.
- `task_loader.py`: per-load source compilation and temporary import resolution for
  workspace-local absolute/relative imports without permanent `sys.path` or module
  cache changes.
- `workspace_manifest.py`: strict portable `.yadof/workspace.json` schema carrying
  workspace, package, template, and rawData contract versions without installation
  paths.
- `workspace_init.py`: validates bundled template metadata/content, checks exact
  target conflicts, creates a staged workspace, validates config/task/workflow
  syntax, and publishes without overwrite. The marker is published last for an
  existing directory and created files are rolled back on failure.
- `workspace_check.py`: report-only structure/marker/config/task/static-rawData and
  selected-backend diagnostics. It parses but never imports or executes workflow;
  external commands are located with read-only discovery and never invoked.
- `yadof.job_template`: installed `Parameter`, normalization/materialization API,
  rawData contract/views, generic cost helpers, and workspace-explicit task queries.
  User-owned parameter/workflow/cost/adapters/assets remain in the workspace.
- `smoke_test.py`: compares marker-selected task files byte-for-byte with the
  bundled generic template. Only that unchanged generic task runs without
  `--real-task`; edited/additional/external payloads require explicit execution
  intent.

## Packaged Local Evaluate Manager Components

```mermaid
flowchart LR
    EvalAPI["api.py"] --> JobFiles["job_files.py"]
    EvalAPI --> LocalRunner["local_runner.py"]
    EvalAPI --> JobResult["job_result.py"]
    JobFiles --> WorkerFiles["worker_files/worker_misc.py"]
    JobFiles --> Types["types.py"]
    LocalRunner --> JobResult
    JobResult --> Types
    EvalAPI --> DynamicCost["yadof.job_template cost API"]
```

- `api.py`: explicit-workspace population/local-smoke entry points, fresh config
  loading, ordered local concurrency, cost derivation, and per-individual `inf`
  isolation. It has no `project.*` or recorded-data dependency.
- `job_files.py`: collision-safe package/task composition, assigned parameter
  materialization, package worker/config injection, definition-only static hashing,
  and yadof/workspace/config provenance.
- `worker_files/worker_misc.py`: stable copied worker helpers migrated from the old
  task template. Workspace tasks may use the reserved `worker_misc.py` import but
  may not replace that filename.
- `local_runner.py`: subprocess execution with process-tree timeout, bytecode-cache
  suppression, rawData validation, no-`cost.json` enforcement, and merged workflow/
  runner metadata.
- `job_result.py` and `types.py`: preserved `JobSpec`/`JobResult` and metadata/result
  handoff shapes for local now and distributed later.

## Optimize Components

```mermaid
flowchart LR
    OptAPI["api.py"] --> GPSAF["gpsaf.py"]
    GPSAF --> Pymoo["gpsaf_pymoo.py"]
    GPSAF --> Phases["gpsaf_phases.py"]
    GPSAF --> Misc["gpsaf_misc.py"]
    GPSAF --> Problem["problem_info.py"]
    OptAPI --> Runner["runner.py"]
```

- `api.py`: stable entry point.
- `gpsaf.py`: one-generation orchestration.
- `gpsaf_pymoo.py`: GA/NSGA-III ask-tell adapter in normalized space, including Das-Dennis reference-direction selection and NSGA-III survival helpers.
- `gpsaf_phases.py`: surrogate alpha/beta pooled NSGA-III candidate selection, anti-starvation exploration quota, uncertainty diagnostics, and fallback.
- `gpsaf_misc.py`: history loading, evaluation API calls, cost helpers.
- `problem_info.py`: variable/objective metadata from `job_template.api`.
- `runner.py`: generation metadata helpers.

## Transitional Source Evaluate Manager Components

```mermaid
flowchart LR
    EvalAPI["api.py"] --> JobFiles["job_files.py"]
    EvalAPI --> LocalRunner["local_runner.py"]
    EvalAPI --> CondorRunner["condor_runner.py"]
    EvalAPI --> RDClient["recorded_data_client.py"]
    CondorRunner --> ResourceRequests["resource_requests.py"]
    CondorRunner --> ResourceRetries["resource_retries.py"]
    CondorRunner --> TimeLimits["time_limits.py"]
    LocalRunner --> JobResult["job_result.py"]
    CondorRunner --> JobResult
    JobFiles --> Types["types.py"]
    LocalRunner --> Types
    CondorRunner --> Types
    RDClient --> Types
    EvalAPI --> EvalConfig["project.config.all via evaluate_manager/config.py"]
```

- These `project.evaluate_manager` components remain for the source optimizer,
  recorded-data, and HTCondor transition path. New workspace-local calls use the
  packaged components above; later stages move persistence and distributed pieces.
- `api.py`: backend selection, local per-individual worker-pool coordination, failure isolation, and ordered cost return.
- `job_files.py`: copy the template, ask `job_template.api` to fresh-load and
  materialize one assigned parameter snapshot, copy the cache-free `config/`
  package, write run/generation metadata, and compute the static hash.
- `local_runner.py`: subprocess workflow execution, timeout handling, and job-local `individual_metadata.json` collection.
- `resource_requests.py`: generation-aware adaptive HTCondor memory/disk request
  calculation from recorded Condor measurements; it returns one concrete request
  and CPU remains manual.
- `resource_retries.py`: removable yadof-side state machine for standard HTCondor
  out-of-memory/out-of-disk holds. It doubles only the exhausted resource, bounds
  retries independently, records attempt history, and clears attempt outputs before
  a fresh submission.
- `time_limits.py`: per-job HTCondor execution-limit calculation. Smoke jobs are unlimited; normal jobs use fixed or generation-aware automatic limits from recorded execution time.
- `condor_runner.py`: Windows HTCondor submit-file generation, submission, polling,
  yadof resource-retry orchestration, generation-budget timeout removal,
  `allowed_execute_duration` hold handling, final ClassAd resource/time collection,
  and job-local result collection. Submit files contain no Condor-native resource
  retry directives.
- `job_result.py`: shared metadata, rawData discovery, and `JobResult` construction helpers used by local and HTCondor backends.
- `recorded_data_client.py`: adapter to `recorded_data.api`.
- `types.py`: immutable job handoff objects.
- `config.py`: generic evaluation settings accessors. Its refresh path reloads the
  active extensions exposed by `config.specific` before the full config surface,
  without naming a simulator-specific module.

## Job Template Components

```mermaid
flowchart LR
    JTAPI["api.py"] --> Params["parameters_constraints.py"]
    JTAPI --> ParamClass["parameters_constraints_class.py"]
    JTAPI --> Cost["calc_cost.py"]
    JTAPI --> Copy["copy_job_files"]
    Copy --> ActiveCom["hfss_com.py"]
    Workflow["workflow.py"] --> HFSSCom["hfss_com.py"]
    Workflow --> RawContract["rawdata_contract.py"]
    Cost --> RawContract
    ComLib["project/com_lib/hfss_com.py and test_com.py"] -. source/reference copies .-> ActiveCom
```

- `parameters_constraints_class.py`: current parameter definitions plus per-job
  `normalized_value` and raw `value` assignment, forward denormalization, and reverse
  normalization for historical raw variables.
- `api.py`: fresh parameter-file loading, current parameter queries, job-local
  parameter materialization, definition-only hash signatures, cost calculation, and
  job copying.
- `workflow.py`: passes the assigned job-local `parameters_constraints.py` snapshot
  directly to the simulator adapter, produces flat rawData output, owns
  `individual_metadata.json` lifecycle timestamps, and loads runtime HFSS defaults
  from job-local config/environment.
- `calc_cost.py`: task-owned rawData-to-cost logic plus optional rawData importance weights for surrogate training. It decides the current objective names/count and may select objective-relevant windows from richer rawData at calculation time.
- `rawdata_contract.py`: `.npz` schema validation.
- `hfss_com.py`: optional HFSS/PyAEDT simulator adapter. A workflow can copy it into `job_template` for active use, while `project/com_lib/hfss_com.py` keeps the synchronized reusable reference copy.
- `project/com_lib/test_com.py`: retained pure-Python simulator stand-in; it must be copied into `job_template` before a workflow can use it.

## Recorded Data Components

```mermaid
flowchart LR
    RDAPI["api.py"] --> Records["records.py"]
    RDAPI --> Query["query.py"]
    Records --> MetaStore["manifest_store.py"]
    Query --> MetaStore
    Records --> RawStore["rawdata_store.py"]
    Query --> RawStore
    MetaStore --> Paths["paths.py"]
```

- `records.py`: compact individual metadata creation, optimization metadata creation, workflow timing promotion, and rawData archiving.
- `query.py`: normalized variables, costs, history, training data, diagnostics.
- `manifest_store.py`: JSONL locking, append/rewrite helpers, and status normalization.
- `rawdata_store.py`: `rawData.npz` member archiving, repeated-variable metadata scrubbing, metadata extraction, and archive loading.

## Surrogate Components

```mermaid
flowchart LR
    SurAPI["api.py"] --> Runtime["runtime.py"]
    SurAPI --> Scheduler["scheduler.py"]
    Scheduler --> Runtime
    Runtime --> Modeling["modeling.py"]
    Runtime --> CheckpointIO["checkpoints.py"]
    Runtime --> SurMeta["metadata.py"]
    Runtime --> RD["recorded_data.api"]
    Runtime --> JT["job_template.api"]
    Runtime --> Checkpoints["surrogate/checkpoints"]
    Modeling --> Checkpoints
```

- `runtime.py`: optimizer-facing service boundary; loads training data, flattens rawData into query-aligned numeric slots, applies task-owned importance weights, scales targets, reconstructs predicted rawData, calculates audited costs and ensemble member min/max intervals, and delegates checkpoint/metadata writes.
- `scheduler.py`: staggered training coordinator; starts background training after real jobs are submitted, waits for pending work when lag limits require it, and exposes latest-state freshness checks.
- `checkpoints.py`, `metadata.py`, and `types.py`: checkpoint serialization, recorded surrogate-training metadata, and shared surrogate dataclasses/type aliases.
- `modeling.py`: PyTorch conditional INR deep ensemble; owns Fourier coordinate features, field embeddings, importance-weighted stochastic query minibatches for large fields, weighted relative/full-field losses, member bootstrap/mixup training, member prediction, and model artifacts.
- `api.py`: stable optimizer-facing exports.
