# C4 Container

## Containers

```mermaid
flowchart TD
    Config["project/config.py"] --> Optimize["project/optimize"]
    Config --> Evaluate["project/evaluate_manager"]
    Config --> Surrogate["project/surrogate"]

    Optimize -->|evaluate population| Evaluate
    Optimize -->|read history| Recorded["project/recorded_data"]
    Optimize -->|optional predict/train| Surrogate

    Evaluate -->|copy template, denormalize| Template["project/job_template"]
    User -->|optionally stages adapter files| ComLib["project/com_lib"]
    Evaluate -->|create/run locally or submit to HTCondor| Jobs["project/jobs runtime folders"]
    Jobs -->|workflow writes rawData and individual metadata| Jobs
    Evaluate -->|read job metadata, record result| Recorded

    Recorded -->|normalize variables, calculate cost| Template
    Surrogate -->|training data| Recorded
    Surrogate -->|rawData to cost| Template

    Tools["project/tools"] -->|inspect via public API| Recorded
    Tests["project/test"] -->|verify contracts| Optimize
    Tests --> Evaluate
    Tests --> Template
    Tests --> Recorded
    Tests --> Surrogate
```

## Container Responsibilities
- `optimize`: NSGA-III search policy for multi-objective runs, history warm start, GPSAF-style surrogate assistance, generation metadata, and evaluation run/generation context.
- `evaluate_manager`: job preparation, local execution, optional HTCondor submission, workflow metadata collection, failure isolation, recording handoff.
- `job_template`: task-specific parameter definitions, workflow, rawData schema, and cost calculation.
- `com_lib`: optional holding area for simulator/custom-code adapter source/reference copies. Files here are not runtime dependencies; when a task needs one, the user copies it into `job_template` so prepared jobs stay self-contained.
- Current default `job_template`: HFSS/PyAEDT `Metal_recon_ant.aedt` rawData generation plus four bounded reference objectives calculated after recording.
- `recorded_data`: durable real-evaluation archive and dynamic historical views.
- `surrogate`: rawData-first conditional INR ensemble training, audited rawData prediction, and ensemble member min/max cost interval generation.
- `tools`: optional user workflows for visualization and maintenance.
- `test`: local verification of contracts and failure behavior.

## Primary Data Flow
1. `optimize` creates normalized candidates.
2. `evaluate_manager` prepares one job per candidate and denormalizes through `job_template`.
3. Job `workflow.py` runs either as a local subprocess or HTCondor payload, imports adapter files copied from `job_template`, writes `individual_metadata.json` at start/end, and writes flat rawData `.npz` files.
4. `evaluate_manager` reads job-local metadata and sends job results to `recorded_data`.
5. `recorded_data` stores raw evidence once per individual, archives rawData, and asks `job_template` for dynamic cost when needed.
6. `surrogate` trains a conditional INR ensemble from recorded rawData, with task-owned importance weights for objective-relevant windows, and predicts rawData for optimizer-side candidate screening.

## Container Rules
- Core modules communicate through each other's `api.py` files.
- `config.py` may be imported directly as a small shared settings surface.
- `tools` may be flexible, but core modules and tests must not depend on tools.
- `jobs` folders are runtime state, not source modules.
