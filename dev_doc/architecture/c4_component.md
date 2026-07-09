# C4 Component

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

## Evaluate Manager Components

```mermaid
flowchart LR
    EvalAPI["api.py"] --> JobFiles["job_files.py"]
    EvalAPI --> LocalRunner["local_runner.py"]
    EvalAPI --> CondorRunner["condor_runner.py"]
    EvalAPI --> RDClient["recorded_data_client.py"]
    LocalRunner --> JobResult["job_result.py"]
    CondorRunner --> JobResult
    JobFiles --> Types["types.py"]
    LocalRunner --> Types
    CondorRunner --> Types
    RDClient --> Types
    EvalAPI --> EvalConfig["config_all.py via evaluate_manager/config.py"]
```

- `api.py`: backend selection, local per-individual worker-pool coordination, failure isolation, and ordered cost return.
- `job_files.py`: copy template, copy `config.py` and `config_all.py`, write job input and run/generation context, compute static hash.
- `local_runner.py`: subprocess workflow execution, timeout handling, and job-local `individual_metadata.json` collection.
- `condor_runner.py`: Windows HTCondor submit-file generation, submission, polling, timeout removal, and job-local result collection.
- `job_result.py`: shared metadata, rawData discovery, and `JobResult` construction helpers used by local and HTCondor backends.
- `recorded_data_client.py`: adapter to `recorded_data.api`.
- `types.py`: immutable job handoff objects.

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

- `workflow.py`: raw variable input to flat rawData output plus workflow-owned `individual_metadata.json` lifecycle timestamps and runtime HFSS defaults loaded from job-local config/environment.
- `calc_cost.py`: task-owned rawData-to-cost logic plus optional rawData importance weights for surrogate training. It decides the current objective names/count and may select objective-relevant windows from richer rawData at calculation time.
- `rawdata_contract.py`: `.npz` schema validation.
- `hfss_com.py`: optional HFSS/PyAEDT simulator adapter. A workflow can copy it into `job_template` for active use, while `project/com_lib/hfss_com.py` keeps a source/reference copy.
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
