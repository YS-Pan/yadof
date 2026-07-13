# HFSS Multicore Findings And Next Steps

## Consolidated Finding

The 08 Mixed Order plus Iterative Solver profile failed because HTCondor 25.4
injected `OMP_THREAD_LIMIT` with the provisioned CPU count. Removing only that name
from `STARTER_NUM_THREADS_ENV_VARS` allowed the profile to complete multicore under
the normal Windows slot-user execution path.

The same project already completed multicore in direct local workflow, and other
solver profiles completed multicore under HTCondor. Real jobs now isolate the
trigger to the starter-created OpenMP environment rather than the slot-user
identity, scratch path, desktop, priority, or CPU affinity.

## Deployment Constraint

`run_as_owner=True` must not be used as the solution. The intended deployment spans
many personal/office machines with different owners, and any machine may submit or
execute jobs. The fix must work under:

```text
run_as_owner = False
load_profile = True
```

## Current Ruled-Out Causes

- Old interpreter-as-executable submit form.
- Generic HTCondor submit/transfer/Python failure.
- Generic AEDT startup failure under the slot user.
- Simple request/runtime CPU mismatch in the controlled matrix.
- Small memory request in the controlled matrix.
- Job-local `_home/_appdata/_tmp` redirection as a necessary condition.
- `use_auto_settings=False` alone.
- Empty PyAEDT `allowed_distribution_types=[]` alone.
- `load_profile=False` as a practical slot-user path.
- Under-requesting Condor CPUs as a workaround.

## Production Fix

Configure every HFSS worker with the validated list in
`../20260713_hfss_fix_experiments.md`, reconfigure the startd, and verify the
effective list does not contain `OMP_THREAD_LIMIT`. The repository pool setup and
declared-resource scripts now write this setting, and
`setup_worker_hfss_compat.cmd` updates an existing worker without changing its slot
or pool-role configuration.

## Follow-Up Validation

1. Run one profile 08 two-core acceptance job after configuring each worker.
2. Re-audit the official default thread-variable list after every HTCondor upgrade.
3. Keep `OMP_THREAD_LIMIT` excluded until the same profile passes a controlled run
   with it present on the upgraded HTCondor/AEDT combination.
4. Preserve the one-core fallback for unvalidated workers.

## Evidence To Preserve For Future Runs

- `job.sub`
- `condor.log`
- `stdout.txt` and `stderr.txt`
- `individual_metadata.json`
- AEDT `batch.log`
- PyAEDT log files when returned or captured live
- generated ACF files, especially `pyaedt_config.acf`
- `whoami`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `_CONDOR_SCRATCH_DIR`
- Condor allocated `Cpus`, `Memory`, `Disk`, slot name, and execute scratch

## Current Bottom Line

The project keeps the slot-user HTCondor design. Multicore profile 08 is supported
on workers where `OMP_THREAD_LIMIT` has been removed from
`STARTER_NUM_THREADS_ENV_VARS` and a real acceptance job has passed.
