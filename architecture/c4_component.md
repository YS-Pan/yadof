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
- `gpsaf_pymoo.py`: GA/NSGA2 ask-tell adapter in normalized space.
- `gpsaf_phases.py`: surrogate alpha/beta candidate phases and fallback.
- `gpsaf_misc.py`: history loading, evaluation API calls, cost helpers.
- `problem_info.py`: variable/objective metadata from `job_template.api`.
- `runner.py`: generation metadata helpers.

## Evaluate Manager Components

```mermaid
flowchart LR
    EvalAPI["api.py"] --> JobFiles["job_files.py"]
    EvalAPI --> LocalRunner["local_runner.py"]
    EvalAPI --> RDClient["recorded_data_client.py"]
    JobFiles --> Types["types.py"]
    LocalRunner --> Types
    RDClient --> Types
    EvalAPI --> EvalConfig["config.py"]
```

- `job_files.py`: copy template, write job input, compute static hash.
- `local_runner.py`: subprocess workflow execution and timeout handling.
- `recorded_data_client.py`: adapter to `recorded_data.api`.
- `types.py`: immutable job handoff objects.

## Job Template Components

```mermaid
flowchart LR
    JTAPI["api.py"] --> Params["parameters_constraints.py"]
    JTAPI --> ParamClass["parameters_constraints_class.py"]
    JTAPI --> Cost["calc_cost.py"]
    Workflow["workflow.py"] --> TestCom["test_com.py"]
    Workflow --> RawContract["rawdata_contract.py"]
    Cost --> RawContract
    HFSS["hfss_com.py"] -. future adapter .-> Workflow
```

- `workflow.py`: raw variable input to flat rawData output.
- `calc_cost.py`: rawData to three bounded objective costs.
- `rawdata_contract.py`: `.npz` schema validation.
- `test_com.py`: current pure-Python simulator stand-in.
- `hfss_com.py`: real simulator adapter reference surface.

## Recorded Data Components

```mermaid
flowchart LR
    RDAPI["api.py"] --> Records["records.py"]
    RDAPI --> Query["query.py"]
    Records --> Manifest["manifest_store.py"]
    Query --> Manifest
    Records --> RawStore["rawdata_store.py"]
    Query --> RawStore
    Manifest --> Paths["paths.py"]
```

- `records.py`: record creation and rawData copy.
- `query.py`: normalized variables, costs, history, training data, diagnostics.
- `manifest_store.py`: locking, schema, atomic JSON writes.
- `rawdata_store.py`: `.npz` metadata and file loading.

## Surrogate Components

```mermaid
flowchart LR
    SurAPI["api.py"] --> Runtime["runtime.py"]
    Runtime --> RD["recorded_data.api"]
    Runtime --> JT["job_template.api"]
    Runtime --> Checkpoints["surrogate/checkpoints"]
```

- `runtime.py`: training-data load, rawData flattening, RBF/IDW ensemble, prediction, intervals, checkpoints.
- `api.py`: stable optimizer-facing exports.
