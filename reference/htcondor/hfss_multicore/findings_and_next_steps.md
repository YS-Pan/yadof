# HFSS Multicore Findings And Next Steps

## Consolidated Finding

The 08 Mixed Order plus Iterative Solver profile is unstable when HFSS uses more
than one core under Windows HTCondor slot-user execution.

The same project can complete multicore in direct local workflow, and other solver
profiles can complete multicore under HTCondor. The problem is not simply "HFSS is
broken" or "HTCondor cannot run HFSS"; it is a narrower interaction between this
solver profile, multicore HFSS, and the Condor slot-user context.

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

## Operational Workarounds

- For the 08 Mixed Order plus Iterative Solver profile under HTCondor, keep
  `HFSS_JOB_CPUCORE = 1`.
- Use a Direct Solver profile when multicore HTCondor throughput is more important
  than preserving the exact 08 solver configuration.
- Run the 08 multicore workflow directly on a local desktop when that is acceptable.

## Future Fix Directions Within Policy

These directions keep slot-user execution and do not rely on owner execution.

1. Build a repeatable worker slot-user AEDT preflight that starts AEDT under the
   slot user, records HKCU/Ansys profile state, and confirms a tiny solve before
   production runs.
2. Investigate whether a neutral AEDT profile or ACF template can be installed per
   worker for slot users without copying a specific desktop owner's HKCU state.
3. Test narrower ACF/DSO variants that preserve multicore but avoid only the
   unstable HFSS distribution path, rather than disabling all distribution types.
4. Capture `hf3d` crash dumps or Windows Error Reporting artifacts for the 08
   multicore slot-user crash and compare them with direct local multicore solves.
5. If no slot-user multicore fix is found, encode this as a task-level policy:
   this solver profile uses one core under HTCondor, while other solver profiles may
   use multicore after smoke validation.

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

The project should keep the slot-user HTCondor design and treat the 08 multicore
failure as a solver/profile/runtime-context compatibility problem. The safe current
workaround is one HFSS core for that exact profile under HTCondor.
