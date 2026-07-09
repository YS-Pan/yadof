# HFSS Condor Multicore Diagnosis Reference

## Scope

This reference consolidates the archived task
`dev_doc/obsolete/20260708_200950_hfss-condor-iterative-multicore.md`,
the completed diagnosis record
`dev_doc/change_records/20260709_154004_hfss-condor-multicore-diagnosis.md`,
and the follow-up direct local workflow tests run on 2026-07-09.

The target problem is narrow:

- 08 project: `temp/huangzetao20260708.aedt`, Mixed Order basis functions, Iterative Solver.
- 09 project: `temp/huangzetao20260709.aedt`, First Order basis functions, Direct Solver.
- Both are run through the YADOF job workflow that opens `Newchoke20260620.aedt`,
  solves `Setup1`, and exports raw data for three pin states.

## Key Finding

The 08 project can complete a 6-core run when the prepared job is executed directly
as a local `workflow.py` job. The same 08 project fails reproducibly when launched
through HTCondor with more than one HFSS core.

This means the current evidence does not support "08 cannot use multiple cores" as
an intrinsic project-file limitation. The failure surface is the intersection of:

- the 08 Mixed Order plus Iterative Solver profile;
- multi-core HFSS solving;
- the HTCondor-launched Windows execution context.

The 09 Direct Solver profile remains a working control in both HTCondor and direct
local workflow mode.

## Controlled HTCondor Matrix

These runs used worker `DESKTOP-DERG5LD`, `requirements = (OpSys == "WINDOWS")`,
`request_memory = 16GB`, Python `C:\PROGRA~1\PYTHON~1\python.exe`, and
`ParallelTasks = 1`. `request_cpus` and runtime `YADOF_HFSS_JOB_CPUCORE` were kept
equal for each run.

| Project | Solver profile | Cores | Status | Condor return | Peak memory MB | Job |
| --- | --- | ---: | --- | --- | ---: | --- |
| 08 | Mixed Order + Iterative Solver | 1 | done | `0x00000000` | 2837 | `job_20260709_143451_656536` |
| 08 | Mixed Order + Iterative Solver | 2 | error | `0x00000001` | 811 | `job_20260709_144952_269490` |
| 08 | Mixed Order + Iterative Solver | 6 | error | `0x00000001` | 910 | `job_20260709_145457_968577` |
| 09 | First Order + Direct Solver | 2 | done | `0x00000000` | 5590 | `job_20260709_150003_769123` |
| 09 | First Order + Direct Solver | 6 | done | `0x00000000` | 8500 | `job_20260709_152504_029544` |

The ignored diagnostic summary was written to
`temp/hfss_condor_multicore_diag_active4/diagnostic_summary.md`.

## HTCondor Failure Signature

The 08 2-core and 6-core jobs failed during the first adaptive solve. Python exited
with return code 1 because `hfssApp.analyze_setup(...)` returned false and the
workflow raised `RuntimeError: analyze_setup returned False for 'Setup1'`.

The Ansys batch logs show the solver-level crash:

- 08 2-core: `process hf3d exited with code -1073741819` at 2026-07-09 14:50:49.
- 08 6-core: `process hf3d exited with code -1073741819` at 2026-07-09 14:55:51.

Windows Event Log on the worker recorded matching Application Error and Windows Error
Reporting entries. Both identify `hf3d.exe` version `2024.1.0.1`, exception
`0xc0000005`, and fault offset `0x000000000202a604`.

## Direct Local Workflow Tests

These tests prepared normal job folders and then ran the job workflow locally through
`project.evaluate_manager.local_runner.run_local_job(...)`. They did not submit to
HTCondor and did not use Condor file transfer or a Condor execute directory.

Both tests used:

- `YADOF_HFSS_JOB_CPUCORE=6`
- `YADOF_HFSS_PARALLEL_TASKS=1`
- `YADOF_HFSS_NON_GRAPHICAL=1`
- `ANSYSLMD_LICENSE_FILE=1055@localhost`

The workflow still used job-local runtime directories, so this was not a manual
desktop solve:

- `USERPROFILE` was the job-local `_home`.
- `APPDATA` was the job-local `_appdata`.
- `LOCALAPPDATA` was the job-local `_localappdata`.
- `TEMP`/`TMP` were the job-local `_tmp`.
- `_CONDOR_SCRATCH_DIR` was empty.
- Runtime user was `desktop-derg5ld\yspan`.

| Project | Solver profile | Mode | Cores | Status | Return | Raw data files | Start | End | Job |
| --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- |
| 08 | Mixed Order + Iterative Solver | direct local workflow | 6 | done | 0 | 9 | 2026-07-09 16:11:10 | 2026-07-09 16:17:58 | `job_20260709_161110_877546` |
| 09 | First Order + Direct Solver | direct local workflow | 6 | done | 0 | 9 | 2026-07-09 16:17:58 | 2026-07-09 16:31:20 | `job_20260709_161758_127745` |

The ignored local summary was written to
`temp/hfss_local_workflow_6core_20260709_161110/local_workflow_6core_summary.md`.
The Application event log was checked for 2026-07-09 16:10:00 through 16:35:00 and
no matching `hf3d`, `ansysedt`, Ansys, or Windows Error Reporting crash events were
found.

## Direct Local Evidence Details

For 08, all three `analyze_setup` calls solved correctly:

- pin state 1: PyAEDT reported `Design setup Setup1 solved correctly in 0.0h 2.0m 12.0s`.
- pin state 2: PyAEDT reported `Design setup Setup1 solved correctly in 0.0h 1.0m 49.0s`.
- pin state 3: PyAEDT reported `Design setup Setup1 solved correctly in 0.0h 2.0m 13.0s`.

For 09, all three `analyze_setup` calls solved correctly:

- pin state 1: PyAEDT reported `Design setup Setup1 solved correctly in 0.0h 3.0m 30.0s`.
- pin state 2: PyAEDT reported `Design setup Setup1 solved correctly in 0.0h 4.0m 10.0s`.
- pin state 3: PyAEDT reported `Design setup Setup1 solved correctly in 0.0h 5.0m 5.0s`.

Both local jobs produced the same raw data file set:

- `axial_ratio_pinState1.npz`, `axial_ratio_pinState2.npz`, `axial_ratio_pinState3.npz`
- `gain_lhcp_pinState1.npz`, `gain_lhcp_pinState2.npz`, `gain_lhcp_pinState3.npz`
- `s11_pinState1.npz`, `s11_pinState2.npz`, `s11_pinState3.npz`

The only stderr content in both local tests was the PyAEDT/EMIT compatibility warning
for Python 3.13. It did not affect the solve.

## Interpretation

The combined evidence rules out several earlier suspects:

- It is not a submit/runtime CPU mismatch. The controlled Condor matrix matched
  `request_cpus` and `YADOF_HFSS_JOB_CPUCORE`.
- It is not a small memory request. All controlled Condor runs requested 16GB, and
  the failing 08 multi-core runs peaked below 1GB.
- It is not a generic failure to launch the job template, transfer files, run Python,
  or solve HFSS under Condor. The 08 one-core Condor control and the 09 multi-core
  Condor controls completed.
- It is not an intrinsic inability of the 08 AEDT file or workflow to run with 6 HFSS
  cores. The direct local workflow 08 6-core test completed and exported data.

The strongest current conclusion is:

> The 08 Mixed Order plus Iterative Solver multi-core path is sensitive to the
> Condor-launched Windows execution context. The crash is likely triggered by some
> combination of Condor user/session/service context, execute directory, profile or
> registry initialization, environment block, or generated HFSS DSO/HPC configuration.

The direct local workflow test is especially useful because it also used job-local
profile and temp directories. That narrows the difference from "any job-local profile"
to details specific to Condor launch and its worker context.

## Temp Directory Note

Both successful local workflow jobs and the earlier Condor jobs report
`Temp directory: R:\hfssTemp` in the AEDT batch log header. The workflow records
job-local `_tmp` as runtime `TEMP` and calls PyAEDT `set_temporary_directory()` after
AEDT starts.

Because the successful local workflow jobs and the failing Condor jobs share the same
batch header temp path, that header alone is not enough to explain the crash. A future
test can still force an AEDT startup-level temp or ACF configuration, but the current
evidence says the fixed header path is not the only condition needed for failure.

## Next Fix-Oriented Tests

To solve multi-core under Condor rather than only avoiding it, the next tests should
target the remaining difference between direct local workflow and Condor workflow.

1. Test Condor under the submitting desktop user, if the local HTCondor installation
   supports a safe `run_as_owner=True` setup. Keep the current Windows `load_profile`
   constraints in mind because `condor_runner.py` rejects incompatible combinations.
2. Compare the full environment block for the successful direct local 08 6-core job
   and the failing Condor 08 6-core job, especially `_CONDOR_SCRATCH_DIR`, `PATH`,
   `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, and license variables.
3. Compare AEDT/HFSS DSO state for successful local 08 6-core and failing Condor
   08 6-core. The PyAEDT log line `Key Desktop/ActiveDSOConfigurations/HFSS correctly
   changed` confirms that DSO settings are being touched, but does not prove both
   launches produce equivalent runtime solver distribution settings.
4. Force a stable HFSS HPC/DSO configuration with an ACF file or PyAEDT HPC settings
   instead of relying only on generated desktop state. Then retest the smallest
   failing case: 08, Condor, 2 cores, 16GB.
5. If DSO state is the differentiator, keep 08 Mixed Order plus Iterative Solver and
   restrict only the unstable distribution mode. That would be a real multi-core fix
   when it keeps `YADOF_HFSS_JOB_CPUCORE > 1`.
6. If Condor user/session state is the differentiator, prefer a stable run-as-owner
   or persistent worker profile solution over changing the AEDT project.

## Operational Recommendation

Until the Condor-specific trigger is fixed, production HTCondor runs should continue
to avoid the failing 08 multi-core combination. Safe paths already demonstrated are:

- 08 Mixed Order plus Iterative Solver through HTCondor with one HFSS core.
- 09 First Order plus Direct Solver through HTCondor with 2 or 6 HFSS cores.
- 08 Mixed Order plus Iterative Solver as a direct local workflow job with 6 HFSS cores.

For future debugging, keep memory fixed at 16GB and retest only the smallest failing
Condor case first: 08 with matched 2 requested/runtime cores.
