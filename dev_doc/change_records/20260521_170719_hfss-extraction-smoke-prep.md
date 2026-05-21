# 2026-05-21 17:07 - HFSS Extraction Smoke Prep

## Context
- An interactive VS Code run of `project/tools/hfss_get_para_and_range.py` successfully regenerated `project/job_template/parameters_constraints.py` from `Metal_recon_ant.aedt`.
- The current AEDT design to optimize is `HFSSDesign1`.
- The current task should keep `hfss_com.py` both as a reference/source file in `project/com_lib/` and as the active job-local adapter in `project/job_template/`.

## Change
- Added `project/com_lib/hfss_com.py` as a copy of the active HFSS adapter rather than removing it from `com_lib`.
- Updated parameter-count-sensitive tests to follow `job_template.api.get_variable_count()` where the exact count is not the subject of the test, and updated the explicit default parameter-name test to the 19 variables extracted from `Metal_recon_ant.aedt`.
- Increased the real HFSS smoke-test timeout through `YADOT_HFSS_SMOKE_TIMEOUT_SEC` so AEDT startup and the four pin-state solves have enough time.
- Updated `hfss_com.py` for PyAEDT 0.19 `SolutionData`: modal traces may expose `data_real()` instead of `get_expression_data()`, and far-field full matrices may be dictionaries keyed by sweep coordinates.
- Avoided saving temporary job-local `.aedt` projects on workflow exit; jobs only need rawData outputs, and saving can fail in temporary AEDT workspaces.
- Documented why an AEDT extraction can work in VS Code but fail or return no variables from a sandboxed/incorrect-context command.

## Rationale
- Prepared jobs must be self-contained in local and distributed modes, so workflow imports active adapters from its own job folder, not from repository-level `com_lib`.
- `com_lib` still has value as a user-managed adapter shelf. Keeping a source/reference `hfss_com.py` there makes future task setup explicit: copy the needed adapter into `job_template`.
- HFSS/PyAEDT behavior depends on both the correct design name and the Windows/AEDT user profile used to launch it.

## Impact
- The current default parameter width is 19.
- A real HFSS smoke test should be launched with `YADOT_RUN_HFSS_TESTS=1` and a long timeout, such as `YADOT_HFSS_SMOKE_TIMEOUT_SEC=5400`, on a machine where AEDT can use the normal interactive user profile.
