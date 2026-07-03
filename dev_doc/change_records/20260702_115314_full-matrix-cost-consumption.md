# 2026-07-02 11:53 - Full-Matrix Cost Consumption

## Context
- The HFSS workflow now exports Far Fields as full-matrix rawData to preserve more information for surrogate training.
- `calc_cost.py` still had a trace-oriented curve helper that flattened all remaining dimensions, so full-matrix axial-ratio data could fail cost calculation and return the task error cost.

## Change
- Updated `project/job_template/calc_cost.py` so curve extraction keeps the requested x-axis and reduces any remaining finite dimensions per x-coordinate instead of flattening the whole array.
- Axial-ratio target curves now keep `Freq` as the curve axis after selecting target `Phi` and `Theta`, and conservatively reduce any leftover dimensions with the maximum finite axial-ratio value.
- Replaced the obsolete cost observation-window test fixture with current Newchoke S11, LHCP gain, and axial-ratio rawData mocks, including full-matrix Far Fields.
- Updated architecture and `job_template` blueprint text from the old four-objective Metal_recon wording to the current three-objective Newchoke wording.

## Rationale
- Full-matrix rawData is the right durable evidence for the rawData-first surrogate path. Cost calculation should be a dynamic interpretation of that evidence, not a reason to export less information.
- Keeping objective slicing inside `calc_cost.py` allows surrogate training to see full fields while objective costs remain based on the intended phi/theta/frequency observation windows.

## Impact
- Completed full-matrix HFSS jobs should be cost-calculable by `recorded_data` and `tools/viewCost.py`.
- Trace-style rawData remains compatible because the same helper still works when only one objective axis is present.

## Verification
- `python -m pytest project/test/test_calc_cost_observation_windows.py -q`
- `python -m pytest project/test/test_rawdata_contract.py -q`
- `python -m pytest project/test/test_recorded_data_contract.py -q`
- `python -m pytest project/test/test_view_cost_tool.py -q`
- `python -m pytest project/test/test_calc_cost_observation_windows.py project/test/test_rawdata_contract.py project/test/test_recorded_data_contract.py project/test/test_view_cost_tool.py project/test/test_minimal_closed_loop.py project/test/test_surrogate_optimize_real.py -q`
- `python -m py_compile project/job_template/calc_cost.py project/job_template/workflow.py project/job_template/hfss_com.py project/com_lib/hfss_com.py`
- Submitted one HTCondor smoke job with `run_id='codex_smoke_20260702_full_matrix'`; it completed as `job_20260702_120119_306153` and returned costs `(0.008741348496388857, 0.6593326556814012, 0.2181813795470382)`.
- Verified recorded full-matrix Far Fields for the smoke job: LHCP gain files have `data_contract="grid"` and shape `[1, 73, 73]`; axial-ratio files have `data_contract="grid"` and shape `[5, 73, 73]`.
- `project/tools/run_viewcost.bat` now finds completed rows and wrote `project/tools/cost_20260702_120745.png`.
