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
- Per-job workflow lifecycle metadata: `project/jobs/<job_name>/individual_metadata.json`, written by the workflow and read by `evaluate_manager` during finalization.
- Recorded individual metadata: `project/recorded_data/indMeta.jsonl`.
- Recorded rawData: `project/recorded_data/rawData.npz`, a zip-based archive with members shaped like `job_name/file.npz`.
- Recorded optimization metadata: `project/recorded_data/optMeta/optMeta.jsonl`.
- Surrogate checkpoints: `project/surrogate/checkpoints/generation_*.json`.
- Surrogate model artifacts: `project/surrogate/checkpoints/generation_*_conditional_inr/` containing `inr_meta.json`, `member_*.pt`, and auxiliary target-scaling/query-table payloads.
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
- `created_at` is not part of the individual record contract; job creation time can be inferred from time-based job folder names when needed.
- `recorded_data` JSONL metadata writes and rawData archive updates must stay atomic because future distributed finalization may introduce more concurrency.
