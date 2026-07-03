# 2026-07-02 11:05 - HFSS Far-Field Export Fix

## Context
- Distributed HFSS jobs reached post-processing but failed while exporting `dB(RealizedGainLHCP)`.
- PyAEDT returned `False` from `get_solution_data`, and AEDT logs reported no trace data for the LHCP gain quantity.
- Because every job was recorded as `error`, `tools/viewCost.py` found no `status='completed'` historical rows.

## Change
- Updated `project/job_template/workflow.py` so S11 still uses `Setup1 : Sweep`, LHCP gain uses `Setup1 : LastAdaptive`, axial ratio uses `Setup1 : Sweep`, and far-field exports use the active AEDT far-field setup name `Infinite Sphere1`.
- Kept normal workflow Far Fields as full-matrix rawData: LHCP gain exports full `Theta/Phi` coverage at the target frequency, and axial ratio exports full `Theta/Phi/Freq` coverage.
- Updated `project/job_template/hfss_com.py` and `project/com_lib/hfss_com.py` so explicit far-field `primary_sweep_variable` requests are passed through to PyAEDT and exported as trace-style rawData, while omitted `primary_sweep_variable` still defaults to full-matrix reconstruction.
- Updated `project/tools/run_viewcost.bat` so it activates the `yadof` environment, works when launched from outside `project/tools`, and falls back to `C:\ProgramData\miniconda3` when `conda` is not on `PATH`.
- Updated the `job_template` blueprint with the task-specific far-field full-matrix contract plus trace compatibility behavior.
- Updated the `tools` blueprint with the runner batch-file behavior.

## Rationale
- In `Newchoke20260620.aedt`, LHCP gain is available under the `LastAdaptive` solution and the far-field setup is named `Infinite Sphere1`, not `3D`.
- The current cost function reads objective windows from the exported rawData, but the surrogate intent is to retain more full-field information than the objective windows alone. Keeping full-matrix workflow exports preserves that information while allowing `calc_cost.py` to select the target phi/theta/frequency points dynamically.

## Impact
- New jobs should produce complete S11, LHCP gain, and axial-ratio rawData for all configured pin states, with Far Fields stored as full-matrix rawData unless a task explicitly requests trace mode.
- Once at least one job completes and is recorded, `run_viewcost.bat` should have `status='completed'` rows to inspect.
- `run_viewcost.bat` can now be launched from the repository root in a plain shell on the current workstation.

## Follow-Up
- Real HTCondor smoke testing should confirm that AEDT/PyAEDT returns the expected full-matrix contract on worker machines.
