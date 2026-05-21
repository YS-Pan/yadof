# 2026-05-21 13:18 - HFSS Metal Recon Task

## Context
- The project moved from the synthetic `test_com` task to the real HFSS task in `reference/20260319 huangzetao`.
- The new task must preserve the v3 invariant that workflow writes rawData only and cost is calculated dynamically from `job_template/calc_cost.py`.

## Change
- Replaced the placeholder `xxxx.aedt` template with `Metal_recon_ant.aedt`.
- Added simulator adapters under `project/com_lib/`, with an active `hfss_com.py` copy in `project/job_template/` used by the current workflow and `test_com.py` retained as a synthetic adapter reference.
- Rewrote `job_template/workflow.py` to run HFSS pin-state simulations and write flat schema-valid S11/gain rawData without `cost.json`.
- Rewrote `job_template/calc_cost.py` to implement the old huangzetao objectives: S11 band, gain steering, gain split, and broadside gain.
- Migrated `hfss_get_para_and_range.py` into `project/tools/` and adapted it to regenerate `job_template/parameters_constraints.py` using the v3 `Parameter` class.
- Updated tests and docs for the HFSS task contract.
- The initial automated parameter-extraction attempt used an unsuitable AEDT context and reported no optimization-enabled variables; a later interactive VS Code run against design `HFSSDesign1` regenerated the current parameter file successfully.

## Rationale
- Keeping HFSS execution in workflow and objective calculation in `calc_cost.py` allows historical rawData to be reinterpreted if objectives change.
- Keeping adapter reference copies in `com_lib` separates reusable simulator glue from task template contracts; placing an active copy in `job_template` keeps prepared jobs standalone.

## Impact
- Default real evaluation now requires PyAEDT/AEDT and the current `Metal_recon_ant.aedt` template.
- Ordinary tests skip the real HFSS smoke path unless `YADOT_RUN_HFSS_TESTS=1` is set.
- The default parameter count is now 19 and the objective count is now 4.

## Follow-Up
- Run a real HFSS smoke evaluation on a machine with AEDT configured.
- If AEDT-side optimization flags are required for future parameter extraction, enable them in the `.aedt` project or extend the tool to read the desired variable/range source.
- If additional simulator families are needed, add new adapters under `project/com_lib/`, copy the active adapter into `project/job_template/`, and keep core modules unchanged.
