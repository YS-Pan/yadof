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

    O->>E: evaluate_population(normalized population, run/generation context)
    E->>T: denormalize through job_template.api
    E->>J: copy template, write job_input.json and submit-side metadata
    E->>J: run workflow.py subprocess
    J->>T: workflow reads raw variables
    T->>J: write individual_metadata.json started_at
    T->>J: write flat rawData/*.npz
    T->>J: update individual_metadata.json ended_at/status
    E->>J: read individual_metadata.json
    E->>R: record_job_result(job, raw variables, rawData paths, merged metadata)
    R->>R: append compact indMeta row, archive rawData members
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

## Distributed Evaluation Sequence

```mermaid
sequenceDiagram
    participant O as optimize
    participant E as evaluate_manager
    participant C as condor_runner
    participant H as HTCondor
    participant J as job folder
    participant R as recorded_data

    O->>E: evaluate_population(..., mode="distributed")
    E->>J: prepare all job folders with the local job contract
    E->>C: submit prepared jobs
    C->>J: write job.sub with executable = workflow.py
    C->>H: condor_submit job.sub
    H->>J: return rawData/ and individual_metadata.json on exit
    C->>J: poll condor.log and job-local outputs
    C-->>E: JobResult rows
    E->>R: record_job_result through the shared finalization path
    E-->>O: dynamic cost rows or inf rows
```

## Failure Handling
- Prepare failure: `evaluate_manager` creates a synthetic failure result if possible, records best effort, and returns `inf`.
- Workflow failure: `workflow.py` writes failure status and `ended_at` into `individual_metadata.json` when it can; local runner adds return code, stdout/stderr tails, and rawData presence.
- Submit failure: HTCondor submission errors are captured as per-job `error` metadata. The project does not attempt to repair the local HTCondor installation.
- Timeout: local runner terminates the process tree; HTCondor runner best-effort removes the submitted cluster id. Both record status `timeout` and preserve any returned job-local metadata.
- Record failure: evaluation continues; returned row becomes `inf`.
- Invalid rawData: `recorded_data.query` skips invalid completed rawData for history/training and exposes diagnostics.

## Concurrency Notes
- Current local evaluation is sequential at the API level.
- `recorded_data` JSONL metadata writes and rawData archive updates are protected by process-local and file-level locks.
- Distributed mode reuses the same record/finalize semantics: workers write job-local individual metadata and submit-side finalizers send compact records to `recorded_data`.
