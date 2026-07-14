# 2026-07-14 16:50 - Retire Resolved HFSS Condor Diagnosis Script

## Context

`project/tools/hfss_condor_multicore_diagnose.py` was a 895-line, one-purpose
experiment runner for the historical 08/09 HFSS multicore failure. It required two
specific ignored AEDT files under `temp/`, submitted real diagnostic jobs, and
collected local and execute-machine Windows Event Logs.

The investigation is complete. The validated production fix removes
`OMP_THREAD_LIMIT` from the worker starter configuration; its evidence and
deployment procedure are retained under `admin_tool/htcondor/` and
`admin_tool/htcondor_pool/`.

## Change

- Removed `project/tools/hfss_condor_multicore_diagnose.py`.
- Removed the script-specific behavior and I/O notes from the `tools` blueprint.

## Rationale

The script neither served a normal user workflow nor provided a reusable
administrator operation. Its fixed 08/09 inputs are absent from the repository,
and project runtime code and tests do not depend on it. Keeping its conclusions in
administrator documentation preserves the durable operational knowledge without
retaining a costly, obsolete experiment runner.

## Impact

`project/tools/` now contains only maintained user-facing tools. Administrators
configure the resolved HFSS compatibility setting through
`admin_tool/htcondor_pool/setup_worker_hfss_compat.cmd`.

## Follow-Up

None.
