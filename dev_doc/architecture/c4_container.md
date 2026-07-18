# C4 containers

```mermaid
flowchart LR
    User["User / CLI"] --> Package["installed yadof package"]
    User --> Workspace["explicit writable workspace"]
    Package --> Workspace
    Package --> Local["local Python worker"]
    Package --> Condor["HTCondor submit tools"]
    Condor --> Worker["slot-user worker"]
    Workspace --> Local
    Workspace --> Condor
    Local --> Workspace
    Worker --> Workspace
```

The package owns defaults, config validation, task loading, job composition,
optimization, evaluation backends, rawData-first persistence/surrogate logic, tools,
worker support, templates, adapters, and docs. Each workspace owns root `config.py`,
`job_template/`, jobs, recorded evidence, checkpoints, logs, and tool output.

Prepared jobs merge a current workspace task payload with package worker resources.
Local and distributed results converge on the same `JobResult`, rawData validation,
recording, current-cost derivation, failure isolation, and tuple-shape contracts.
