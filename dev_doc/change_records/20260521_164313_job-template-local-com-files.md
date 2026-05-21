# 2026-05-21 16:43 - Job Template Local Com Files

## Context
- `Metal_recon_ant.aedt` now uses design `HFSSDesign1`.
- Jobs may run in distributed mode or under a non-default local jobs path, so workflow code must not depend on importing adapters from repository-level `project/com_lib`.

## Change
- Updated the HFSS workflow design name to `HFSSDesign1`.
- Copied the active `hfss_com.py` adapter into `project/job_template/`.
- Removed automatic copying of root-level `com_lib` from `job_template.api.copy_job_files()`.
- Allowed HTCondor submit input transfer to include `hfss_com.py` as a normal job-template file while still excluding `calc_cost.py`.
- Updated tests and documentation to state that `com_lib` is only a staging/reference area.

## Rationale
- Prepared job folders must be self-contained after template copying, regardless of where `jobs/` lives or whether HTCondor transfers the job sandbox.
- Users should opt into a simulator adapter by moving or copying the chosen com file into `job_template`, making task dependencies explicit.

## Impact
- Current HFSS jobs import `hfss_com.py` from their own job folder.
- `project/com_lib/test_com.py` remains available as a synthetic adapter reference, and `project/com_lib/hfss_com.py` keeps a reference/source copy of the current HFSS adapter; no active workflow imports `project/com_lib` directly.

## Follow-Up
- If future tasks need another adapter, move or copy that adapter into `project/job_template/` before launching optimization.
