# 2026-05-27 10:44 - Worker RAM Disk Execute Script

## Context
- Distributed AEDT optimization should run job scratch directories on each worker machine's `R:` RAM disk.
- The existing HTCondor pool scripts configured manager/worker roles, but did not set the worker-side `EXECUTE` directory.

## Change
- Added `project/tools/htcondor_pool/setup_worker_ramdisk_execute.cmd` as the double-click entry point.
- Added `project/tools/htcondor_pool/configure_worker_ramdisk_execute.ps1` to create `R:\condor_execute`, grant slot-user access, write a managed HTCondor config block, advertise the RAM-disk execute directory, restart HTCondor, and print verification output.
- Documented the step in `project/tools/htcondor_pool/README.md`.
- Updated the tools blueprint with the new worker RAM-disk setup utility.

## Rationale
- Worker scratch placement belongs to HTCondor's execute-side `EXECUTE` setting, not to project `JOBS_DIR`.
- A separate re-runnable worker script keeps the role setup scripts stable and lets machine 1, 3, and 6 all receive the same execute-directory configuration.

## Impact
- Run `setup_worker_ramdisk_execute.cmd` on machine 1, machine 3, and machine 6 after their pool roles are configured.
- Submit-side code and generated `job.sub` files are unchanged.

## Follow-Up
- If some future worker lacks an `R:` RAM disk, constrain `project/config.py` with `HTCONDOR_REQUIREMENTS = '(OpSys == "WINDOWS") && (YADOF_RAMDISK =?= True)'` or run only on machines that advertise `YADOF_RAMDISK`.
