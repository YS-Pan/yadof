# 2026-07-09 17:15 - HFSS Condor Workflow Executable Smoke Setup

## Context
- The active HFSS task needed to use `temp/huangzetao20260708.aedt` while preserving the existing workflow contract that opens `Newchoke20260620.aedt`.
- The requested distributed resources were `1` CPU core, `12GB` memory, and `5GB` disk.
- A real HTCondor smoke first exposed that bare `executable = python` is not reliable on the current Windows worker pool.
- `reference/htcondor_windows_debug_reference.md` records direct `.py` submission as the validated Windows HTCondor pattern.

## Change
- Replaced `project/job_template/Newchoke20260620.aedt` with the bytes from `temp/huangzetao20260708.aedt`.
- Updated `project/config.py` to request `HTCONDOR_REQUEST_CPUS = 1`, `HTCONDOR_REQUEST_MEMORY = "12GB"`, and `HTCONDOR_REQUEST_DISK = "5GB"`.
- Set the current and default HTCondor executable mode to direct workflow submission: `HTCONDOR_EXECUTABLE_MODE = "workflow"`.
- Updated HTCondor submit-file tests and documentation to describe `executable = workflow.py` with `transfer_executable = True` as the default path.

## Rationale
- Keeping the job-local AEDT filename avoids changing the task workflow while changing the underlying simulator project.
- Direct `workflow.py` submission follows the project reference evidence and avoids worker `PATH` or absolute-interpreter assumptions.
- `HFSS_JOB_CPUCORE` remains tied to `HTCONDOR_REQUEST_CPUS`, so the solver core count and scheduler request stay aligned.

## Impact
- New prepared jobs copy the 20260708 AEDT project as `Newchoke20260620.aedt`.
- Default distributed submit files now omit `arguments = workflow.py` and transfer `workflow.py` as the executable.
- Interpreter-style submission remains available only as an explicit fallback by setting `HTCONDOR_EXECUTABLE_MODE = "python"`.

## Verification
- Confirmed `project/job_template/Newchoke20260620.aedt` has the same SHA-256 as `temp/huangzetao20260708.aedt`: `bd5533227d87e6a6769cae96bff1f8bf0fe518cab4ac23d2e84db60107206d93`.
- Confirmed config import resolves to `HTCONDOR_REQUEST_CPUS = 1`, `HTCONDOR_REQUEST_MEMORY = "12GB"`, `HTCONDOR_REQUEST_DISK = "5GB"`, and `HFSS_JOB_CPUCORE = 1`.
- Ran `python -m pytest -q project/test/test_htcondor_distributed_mode.py`: 10 passed.
- Real HTCondor smoke attempt `24643` with `executable = python` reached worker `DESKTOP-A2093` and allocated `1` CPU, `12288` MB memory, and `5242880` KB disk, but was held because the worker tried to execute `scratch\python`.
- A temporary explicit-interpreter smoke attempt `24644` completed successfully with finite costs, proving the replaced AEDT and requested resources can complete under HTCondor, but that submit form is not the intended final executable contract.
- A follow-up real direct-`workflow.py` smoke ran as cluster `24845` on `DESKTOP-A2093`. The generated submit file contained `executable = workflow.py` and `transfer_executable = True`, with `request_cpus = 1`, `request_memory = 12GB`, and `request_disk = 5GB`. HTCondor transferred inputs and started the job on the worker, but the starter held the job before Python/HFSS startup with `Bad exe type. err=193 (errno=8: 'Exec format error')`.
- A targeted diagnostic job `24846` ran on `DESKTOP-A2093` through explicit Python so the payload could inspect the same slot-user scratch context. It confirmed `condor-slot1_1` execution, missing `.py` file association (`assoc .py` failed), missing `Python.File` open command, missing HKCR/HKLM/HKCU `.py` registry bindings, no `.PY` in `PATHEXT`, and no `py.exe` on PATH. Direct CreateProcess-style execution of a copied `.py` reproduced WinError 193, while `C:\ProgramData\miniconda3\envs\yadof\python.exe plain_probe.py` succeeded.

## Follow-Up
- Decide whether production should fall back to interpreter mode, target only workers that can execute `.py` files directly, or update worker file-association / HTCondor executable handling so direct `workflow.py` submission works consistently across the pool.
