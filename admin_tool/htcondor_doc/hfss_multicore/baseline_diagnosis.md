# HFSS Multicore Baseline Diagnosis

> Historical baseline evidence. The failure described here was resolved by the
> later starter-thread setting; see `README.md` for current guidance.

## Scope

This file consolidates the baseline findings from the original HFSS/HTCondor
multicore diagnosis.

Target projects:

- 08: `temp/huangzetao20260708.aedt`, Mixed Order basis functions, Iterative Solver.
- 09: `temp/huangzetao20260709.aedt`, First Order basis functions, Direct Solver.

Both use the same YADOF workflow contract: open `Newchoke20260620.aedt`, solve
`Setup1`, and export rawData for three pin states.

## Key Finding

The 08 project completes a 6-core solve when the prepared job is run directly as a
local `workflow.py` process. The same 08 project fails through HTCondor when HFSS
uses more than one core.

This rules out "the AEDT file cannot use multiple cores" as a standalone
explanation. The remaining failure surface is the Condor-launched Windows execution
context.

## Controlled HTCondor Matrix

These runs used worker `DESKTOP-DERG5LD`, Windows requirements, `request_memory =
16GB`, and `ParallelTasks = 1`. `request_cpus` and runtime
`YADOF_HFSS_JOB_CPUCORE` were kept equal.

| Project | Solver profile | Cores | Status | Condor return | Peak memory MB | Job |
| --- | --- | ---: | --- | --- | ---: | --- |
| 08 | Mixed Order + Iterative Solver | 1 | done | `0x00000000` | 2837 | `job_20260709_143451_656536` |
| 08 | Mixed Order + Iterative Solver | 2 | error | `0x00000001` | 811 | `job_20260709_144952_269490` |
| 08 | Mixed Order + Iterative Solver | 6 | error | `0x00000001` | 910 | `job_20260709_145457_968577` |
| 09 | First Order + Direct Solver | 2 | done | `0x00000000` | 5590 | `job_20260709_150003_769123` |
| 09 | First Order + Direct Solver | 6 | done | `0x00000000` | 8500 | `job_20260709_152504_029544` |

## Failure Signature

The failing 08 multicore HTCondor jobs fail during the first adaptive solve:

- PyAEDT `analyze_setup(...)` returns false.
- The workflow raises `RuntimeError: analyze_setup returned False for 'Setup1'`.
- AEDT `batch.log` reports `process hf3d exited with code -1073741819`.
- Windows event logs identify `hf3d.exe` access violation `0xc0000005`.

## Direct Local Workflow Contrast

Direct local workflow tests used:

- `YADOF_HFSS_JOB_CPUCORE=6`
- `YADOF_HFSS_PARALLEL_TASKS=1`
- `YADOF_HFSS_NON_GRAPHICAL=1`
- `ANSYSLMD_LICENSE_FILE=1055@localhost`

They still used job-local runtime directories:

- `USERPROFILE` under job `_home`;
- `APPDATA` under job `_appdata`;
- `LOCALAPPDATA` under job `_localappdata`;
- `TEMP`/`TMP` under job `_tmp`;
- `_CONDOR_SCRATCH_DIR` empty;
- runtime user `desktop-derg5ld\yspan`.

| Project | Mode | Cores | Status | Raw data files | Job |
| --- | --- | ---: | --- | ---: | --- |
| 08 | direct local workflow | 6 | done | 9 | `job_20260709_161110_877546` |
| 09 | direct local workflow | 6 | done | 9 | `job_20260709_161758_127745` |

All three 08 pin-state solves completed, with solve times around two minutes each.

## Ruled Out By Baseline Evidence

- Not a generic job template, Python, transfer, or result collection failure.
- Not a simple `request_cpus` versus runtime core mismatch in the controlled matrix.
- Not a small memory request; failing 08 multicore jobs requested 16GB and peaked
  below 1GB before crashing.
- Not an intrinsic inability of the 08 AEDT file to run with multiple cores.
- Not explained by the AEDT batch header `Temp directory: R:\hfssTemp`, because the
  successful local workflow and failing Condor jobs share that header.

## Baseline Operational Recommendation

Until the Condor-specific trigger is fixed:

- run the 08 Mixed Order plus Iterative Solver profile through HTCondor with one
  HFSS core;
- use the 09 Direct Solver profile for HTCondor multicore work when acceptable;
- use direct local workflow for 08 multicore runs when local execution is acceptable.
