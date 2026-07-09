# HFSS Condor multicore diagnosis

## Summary
- Added `project/tools/hfss_condor_multicore_diagnose.py` to run controlled HTCondor HFSS smoke matrices from temporary job templates.
- The tool copies `temp/huangzetao20260708.aedt` or `temp/huangzetao20260709.aedt` into an ignored temporary template as `Newchoke20260620.aedt`, so it does not mutate the tracked job template AEDT file.
- The matrix uses matched `request_cpus` and `YADOF_HFSS_JOB_CPUCORE`, a 5 minute polling interval, and one fixed `request_memory = 16GB` for every run.
- On failed runs, it collects Windows Application/System events locally and through a Condor worker-side event probe targeted at the actual execute machine.

## Matrix

All runs used worker `DESKTOP-DERG5LD`, `requirements = (OpSys == "WINDOWS")`, `request_memory = 16GB`, Python `C:\PROGRA~1\PYTHON~1\python.exe`, and `ParallelTasks = 1`.

| Project | Solver profile | Cores | Status | Condor return | Peak memory MB | Job |
| --- | --- | ---: | --- | --- | ---: | --- |
| 08 | Mixed Order + Iterative Solver | 1 | done | `0x00000000` | 2837 | `job_20260709_143451_656536` |
| 08 | Mixed Order + Iterative Solver | 2 | error | `0x00000001` | 811 | `job_20260709_144952_269490` |
| 08 | Mixed Order + Iterative Solver | 6 | error | `0x00000001` | 910 | `job_20260709_145457_968577` |
| 09 | First Order + Direct Solver | 2 | done | `0x00000000` | 5590 | `job_20260709_150003_769123` |
| 09 | First Order + Direct Solver | 6 | done | `0x00000000` | 8500 | `job_20260709_152504_029544` |

The ignored diagnostic summary is under `temp/hfss_condor_multicore_diag_active4/diagnostic_summary.md`.

## Failure Signature

The 08 2-core and 6-core jobs both failed during the first adaptive solve. Python exited with return code 1 because `hfssApp.analyze_setup(...)` returned false and the workflow raised `RuntimeError: analyze_setup returned False for 'Setup1'`.

The underlying Ansys batch logs show the actual solver crash:

- 08 2-core: `process hf3d exited with code -1073741819` at 2026-07-09 14:50:49.
- 08 6-core: `process hf3d exited with code -1073741819` at 2026-07-09 14:55:51.

Windows Event Log on the worker recorded matching Application events:

- 08 2-core: `Application Error` event 1000 at 2026-07-09 14:50:46 and `Windows Error Reporting` event 1001 at 2026-07-09 14:50:49.
- 08 6-core: `Application Error` event 1000 at 2026-07-09 14:55:48 and `Windows Error Reporting` event 1001 at 2026-07-09 14:55:51.

Both event pairs identify `hf3d.exe` version `2024.1.0.1`, exception `0xc0000005`, fault offset `0x000000000202a604`.

## Interpretation

This is not a submit/runtime CPU mismatch: every tested run had matched `request_cpus`, Condor allocated CPUs, and runtime `YADOF_HFSS_JOB_CPUCORE`.

This is not a low-memory failure: all runs requested 16GB, and the two 08 crashes peaked below 1GB. The 09 Direct Solver controls used substantially more memory and still completed.

This is not a generic HTCondor, Python path, slot-user, or transfer failure: 08 succeeds with 1 core under the same runner, and 09 succeeds with both 2 and 6 cores under the same runner, worker, Condor user, profile layout, and transfer contract.

The reproducible failure is specific to the 08 AEDT solver configuration when HFSS uses more than one core under HTCondor: Mixed Order basis functions plus Iterative Solver crash `hf3d.exe` with access violation `0xc0000005` before raw data can be produced.

## Temp Directory Note

The workflow calls PyAEDT `set_temporary_directory()` after AEDT starts and records the runtime `TEMP` as job-local `_tmp`. PyAEDT implements that call as `oDesktop.SetTempDirectory(path)`. AEDT batch log headers still report `Temp directory: R:\hfssTemp`, which appears to be the startup/default desktop temp path rather than proof that the workflow never calls `SetTempDirectory`.

Because 08 one-core and both 09 Direct Solver controls succeed with the same batch header temp path, the observed fixed temp header is not sufficient to explain the multi-core 08 crash. Future Ansys-side debugging can still test an AEDT startup-level temp override or fixed ACF/DSO configuration, but the current project-level safe workaround is to avoid multi-core HFSS for this 08 Mixed Order + Iterative Solver profile.

## Recommendation

Use `HFSS_JOB_CPUCORE = 1` for this exact 08 Mixed Order + Iterative Solver profile when running through HTCondor. If multiple cores are required, use a solver profile equivalent to the 09 Direct Solver control when it is acceptable for the optimization campaign, or treat further ACF/DSO tuning as an Ansys/PyAEDT vendor-side investigation rather than a YADOF submit-path bug.
