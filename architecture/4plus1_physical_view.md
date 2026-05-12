# 4+1 Physical View

## Current Local Deployment

```mermaid
flowchart TD
    Workstation["Windows workstation"]
    Repo["Workspace repo"]
    Python["Python interpreter"]
    Jobs["project/jobs/"]
    Records["project/recorded_data/"]
    Checkpoints["project/surrogate/checkpoints/"]

    Workstation --> Repo
    Repo --> Python
    Python --> Jobs
    Python --> Records
    Python --> Checkpoints
```

## Runtime Locations
- Source code: `project/`.
- Prepared jobs: default `project/jobs/`, configurable by `project/config.py`.
- Recorded rawData: `project/recorded_data/rawData/<job_name>/`.
- Recorded manifest: `project/recorded_data/manifest.json`.
- Surrogate checkpoints: `project/surrogate/checkpoints/`.
- Tool outputs: typically `project/tools/`.

## Future Distributed Deployment

```mermaid
flowchart LR
    Submit["Submit workstation"] --> SharedFS["Shared or synchronized job filesystem"]
    Submit --> Condor["HTCondor scheduler"]
    Condor --> Worker1["Worker node"]
    Condor --> Worker2["Worker node"]
    Worker1 --> SharedFS
    Worker2 --> SharedFS
    Submit --> Records["recorded_data finalization"]
```

## Physical Constraints
- Local tests should not require HTCondor or simulator software.
- Real simulator adapters may require Windows-only COM automation and installed applications.
- Job path should be configurable so users can move high-write runtime folders to faster storage.
- `recorded_data` manifest writes must stay atomic because future distributed finalization may introduce more concurrency.
