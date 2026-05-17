# 4+1 Process View

## Local Evaluation Sequence

```mermaid
sequenceDiagram
    participant O as optimize
    participant E as evaluate_manager
    participant J as job folder
    participant T as job_template workflow
    participant R as recorded_data
    participant C as job_template calc_cost

    O->>E: evaluate_population(normalized population)
    E->>T: denormalize through job_template.api
    E->>J: copy template, write job_input.json, metadata
    E->>J: run workflow.py subprocess
    J->>T: workflow reads raw variables
    T->>J: write flat rawData/*.npz
    E->>R: record_job_result(job, raw variables, rawData paths, metadata)
    R->>R: copy rawData, update manifest
    E->>R: calculate_costs(job_name)
    R->>C: calculate from rawData paths
    C-->>R: costs
    R-->>E: costs
    E-->>O: cost rows
```

## Surrogate-Assisted Generation

```mermaid
sequenceDiagram
    participant O as optimize GPSAF
    participant S as surrogate
    participant R as recorded_data
    participant T as job_template
    participant E as evaluate_manager

    O->>R: get historical optimization results
    O->>S: train(generation_index)
    S->>R: get surrogate training data
    S->>S: flatten rawData, build query table, train conditional INR ensemble
    S->>T: calculate true costs from recorded rawData for audit
    S-->>O: checkpointed state
    O->>S: predict_population(candidate pools)
    S->>S: predict rawData with ensemble mean and member spread
    S->>T: calculate predicted costs from predicted rawData
    S-->>O: costs and intervals
    O->>E: evaluate selected real population
```

## Failure Handling
- Prepare failure: `evaluate_manager` creates a synthetic failure result if possible, records best effort, and returns `inf`.
- Workflow failure: local runner captures return code, stdout/stderr tails, status, and rawData presence.
- Timeout: local runner terminates the process tree and records status `timeout`.
- Record failure: evaluation continues; returned row becomes `inf`.
- Invalid rawData: `recorded_data.query` skips invalid completed rawData for history/training and exposes diagnostics.

## Concurrency Notes
- Current local evaluation is sequential at the API level.
- `recorded_data` manifest writes are protected by process-local and file-level locks.
- Future distributed mode should reuse the same record/finalize semantics.
