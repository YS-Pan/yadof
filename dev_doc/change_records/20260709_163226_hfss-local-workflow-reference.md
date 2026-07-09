# 2026-07-09 16:32 - HFSS Local Workflow Multicore Reference

## Context

The completed HTCondor diagnosis showed that the 08 Mixed Order plus Iterative Solver
project crashes `hf3d.exe` under HTCondor when HFSS uses more than one core. A follow-up
question asked for two direct local workflow tests, one for the 08 project and one for
the 09 project, both using 6 HFSS cores and bypassing Condor submission.

## Change

- Ran direct local job workflow tests for `temp/huangzetao20260708.aedt` and
  `temp/huangzetao20260709.aedt` with `YADOF_HFSS_JOB_CPUCORE=6`.
- Added `reference/hfss_condor_multicore_diagnosis_reference.md`, synthesizing the
  archived toDo, the HTCondor diagnosis record, and the new direct local workflow
  results.

## Result

- 08 direct local workflow 6-core job `job_20260709_161110_877546` completed with
  return code 0 and produced all 9 raw data files.
- 09 direct local workflow 6-core job `job_20260709_161758_127745` completed with
  return code 0 and produced all 9 raw data files.
- The Application event log window from 2026-07-09 16:10:00 through 16:35:00 had no
  matching `hf3d`, `ansysedt`, Ansys, or Windows Error Reporting crash events.

## Rationale

The new tests separate "prepared job workflow" from "HTCondor launch context." Since
the 08 6-core job succeeds when run directly from its prepared job folder, the problem
is not simply that the AEDT file or workflow cannot handle 6 cores. The remaining
failure surface is the Condor-launched Windows execution context interacting with the
08 Iterative Solver multi-core path.

## Impact

No runtime code changed. The new reference document updates the recommended diagnostic
route toward a real Condor multi-core fix: compare Condor versus direct local
environment, user/session/profile state, and generated HFSS DSO/HPC configuration.

## Follow-Up

The smallest next fix-oriented test is 08 through HTCondor with matched 2 requested
and runtime HFSS cores, 16GB memory, and a controlled change to either Condor launch
identity/profile or fixed HFSS DSO/ACF configuration.
