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
- Active simulator adapters copied into jobs: adapter files placed directly in `project/job_template/`.
- Optional adapter staging/reference files: `project/com_lib/`, not copied or imported by default.
- Prepared jobs: submit-side `project/jobs/` by default, configurable by `project/config.py`.
- Per-job workflow lifecycle metadata: `project/jobs/<job_name>/individual_metadata.json`, written by the workflow and read by `evaluate_manager` during finalization.
- Recorded individual metadata: `project/recorded_data/indMeta.jsonl`.
- Recorded rawData: `project/recorded_data/rawData.npz`, a zip-based archive with members shaped like `job_name/file.npz`.
- Recorded optimization metadata: `project/recorded_data/optMeta/optMeta.jsonl`.
- Surrogate checkpoints: `project/surrogate/checkpoints/generation_*.json`.
- Surrogate model artifacts: `project/surrogate/checkpoints/generation_*_conditional_inr/` containing `inr_meta.json`, `member_*.pt`, and auxiliary target-scaling/query-table payloads.
- Tool outputs: typically `project/tools/`.

## Optional Distributed Deployment

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

In the implemented HTCondor path, the submit side writes one `job.sub` per prepared
job folder. The submit file uses the configured worker Python executable with
`arguments = workflow.py`, `transfer_executable = False`, and sandboxed Windows
profile/temp environment variables. It does not set `transfer_output_files`, so
HTCondor returns generated files such as `rawData/`, `individual_metadata.json`,
and PyAEDT-created `batch.log` when they exist without holding the job if optional
files are absent.
Worker scratch placement is controlled by each worker's HTCondor `EXECUTE`
directory. A worker RAM disk such as `R:\condor_execute` should be configured on
the execute machines and advertised through worker ClassAd attributes; it is not
the same setting as the submit-side `JOBS_DIR`.

## Physical Constraints
- Local tests should not require HTCondor or simulator software.
- Distributed tests should mock HTCondor command execution unless they are explicit environment smoke tests.
- Real simulator adapters may require Windows-only COM automation and installed applications.
- The current default task requires PyAEDT/AEDT for real workflow execution; default tests should skip that smoke path unless explicitly enabled.
- Job path should be configurable so users can move high-write runtime folders to faster storage.
- `created_at` is not part of the individual record contract; job creation time can be inferred from time-based job folder names when needed.
- `recorded_data` JSONL metadata writes and rawData archive updates must stay atomic because distributed finalization may introduce more concurrency.
