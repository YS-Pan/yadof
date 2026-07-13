# 2026-07-12 Official HTCondor Docs Review

## Scope

This note records a targeted read of the official HTCondor documentation after the
HFSS multicore debugging work stalled. It focuses on HTCondor configuration and
submit behavior that could plausibly explain a failure which appears only under:

- Windows HTCondor slot-user execution;
- `run_as_owner = False`;
- `load_profile = True`;
- HFSS multicore solve;
- the 08 Mixed Order plus Iterative Solver profile.

This note is information gathering only. It does not change project code.

Follow-up: `20260712_official_docs_deep_dive.md` checks these findings against the
locally installed HTCondor 25.4.0, adds the 25.4 nested-scratch default change and
Windows process priority, and provides the refined experiment order. Use that file
when deciding the next debug run.

## Official Sources Read

Read date: 2026-07-12.

- HTCondor Users' Manual entry point:
  <https://htcondor.readthedocs.io/en/latest/users-manual/index.html>
- HTCondor Administrators' Manual entry point:
  <https://htcondor.readthedocs.io/en/latest/admin-manual/index.html>
- Microsoft Windows platform notes:
  <https://htcondor.readthedocs.io/en/latest/platform-specific/microsoft-windows.html>
- `condor_submit` submit-file reference:
  <https://htcondor.readthedocs.io/en/latest/man-pages/condor_submit.html>
- File transfer mechanism:
  <https://htcondor.readthedocs.io/en/latest/users-manual/file-transfer.html>
- Running-job environment:
  <https://htcondor.readthedocs.io/en/latest/users-manual/env-of-job.html>
- Execution point policy and slots:
  <https://htcondor.readthedocs.io/en/latest/admin-manual/ep-policy-configuration.html>
- Starter daemon configuration:
  <https://htcondor.readthedocs.io/en/latest/admin-manual/configuration/starter.html>
- Automatic job management:
  <https://htcondor.readthedocs.io/en/latest/users-manual/automatic-job-management.html>

The online manual version seen during this pass was 25.11.0.

## Constraints From Existing Project Notes

Keep these constraints from the current `reference/htcondor/` material:

- `run_as_owner=True` is not a production fix path.
- `load_profile=False` already failed early and is not a viable current path for
  AEDT/PyAEDT startup.
- Under-requesting Condor CPUs while asking HFSS for more cores produced a
  different solver out-of-memory failure and is not a workaround.
- Direct `workflow.py` submission with `transfer_executable = True` reproduced the
  crash, so the old interpreter-as-executable pattern is not the main suspect.
- The 09 Direct Solver profile can run multicore under HTCondor, so the failure is
  narrower than "HFSS cannot run under HTCondor".

## Highest-Value New Leads

### 1. HTCondor Injects Thread-Count Environment Variables

HTCondor sets a group of common thread-control environment variables to the number
of cores allocated to the job. The documented defaults include:

```text
CUBACORES
GOMAXPROCS
JULIA_NUM_THREADS
MKL_NUM_THREADS
NUMEXPR_NUM_THREADS
OMP_NUM_THREADS
OMP_THREAD_LIMIT
OPENBLAS_NUM_THREADS
PYTHON_CPU_COUNT
ROOT_MAX_THREADS
TF_LOOP_PARALLEL_ITERATIONS
TF_NUM_THREADS
```

This is a strong suspect because:

- it only changes meaningfully when `request_cpus > 1`;
- it is specific to the HTCondor starter environment;
- `MKL_NUM_THREADS`, `OMP_NUM_THREADS`, and `OMP_THREAD_LIMIT` can affect native
  numerical libraries used by solver components;
- the direct local multicore contrast probably did not run with the same injected
  variable set;
- the 08 profile uses the Iterative Solver, which is more likely than the Direct
  Solver control to use iterative/native math threading paths differently.

Potential experiments:

1. Submit a tiny Condor diagnostic job with `request_cpus = 2` that writes the
   final process environment, `_CONDOR_MACHINE_AD`, and `_CONDOR_JOB_AD`.
2. Try an 08 two-core Condor solve with explicit submit environment overrides:

   ```text
   OMP_NUM_THREADS=1
   OMP_THREAD_LIMIT=1
   MKL_NUM_THREADS=1
   OPENBLAS_NUM_THREADS=1
   NUMEXPR_NUM_THREADS=1
   ```

   Keep `YADOF_HFSS_JOB_CPUCORE=2` for this test. The purpose is to separate HFSS
   DSO/HPC core selection from generic OpenMP/MKL-style thread variables.
3. If submit-file overrides are overwritten by the starter on this HTCondor
   version, test an execute-host admin setting that narrows or clears
   `STARTER_NUM_THREADS_ENV_VARS`.
4. If this fixes the crash, restore variables one at a time to identify the
   sensitive one.
5. Also run the inverse contrast: launch the direct local workflow with the same
   thread variables set to `2`. If the local owner workflow then fails, the lead
   becomes much stronger.

Risk:

- Reducing these variables to `1` may reduce performance in libraries that obey
  them. This is acceptable for diagnosis; a production fix may need a smaller
  targeted list rather than a blanket override.

### 2. Non-Visible Windows Desktop / Window Station

The Windows documentation says HTCondor creates a non-visible Window Station and
Desktop for the job by default. `USE_VISIBLE_DESKTOP=True` lets a job access the
default desktop instead and is described as useful for debugging applications that
do not run correctly under HTCondor.

This is relevant because AEDT/HFSS is a Windows application stack even when called
non-graphically. The crash occurs later in `hf3d`, not at PyAEDT startup, but a
solver child process may still inherit desktop/session differences.

Potential experiment:

- On one isolated worker only, set `USE_VISIBLE_DESKTOP=True` and rerun the 08
  two-core Condor solve under the slot user.

Interpretation:

- If the crash disappears, the issue is probably a Windows desktop/session
  interaction rather than basic Condor file transfer or Python execution.
- This should be treated as a diagnostic result, not automatically as the final
  production configuration. Visible desktop execution changes the security and
  workstation-interaction surface.

### 3. Slot-User Permissions And Local Group

The Windows docs describe the default job identity as a low-privilege dynamic
account named like `condor-slot<X>`, added to the local `Users` group. They also
document `DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP`, which can place the run account in a
different local group.

This is relevant because the 08 crash is under the slot user, and the slot user's
HKCU/profile state is much smaller than the desktop owner's profile. Even if the
observed `hf3d` failure is an access violation rather than a clean access-denied
error, missing ACLs or missing per-user setup can still push native code into a bad
path.

Potential experiments:

1. Create a local group such as `AnsysCondorUsers` on one worker.
2. Grant that group read/execute access to required Ansys, Python, PyAEDT, license,
   and shared runtime locations; grant write access only to intended cache/temp
   locations.
3. Set the worker's `DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP` to that group and reconfig or
   restart HTCondor as required by the changed macro.
4. Rerun the 08 two-core Condor solve under `run_as_owner=False`.

Avoid:

- Do not put slot users into `Administrators` as a first fix. That would hide the
  real dependency and would be risky for a pool of office machines.

### 4. Profile Loading Is Not Persistent Application Setup

`load_profile=True` loads the dedicated run account profile. The Windows docs also
state that the profile is cleaned before a later job uses the dedicated account.

This means an AEDT preflight that modifies HKCU or `%APPDATA%` for a slot account
may not persist in the way an interactive owner's profile does. The current follow-up
already found that the slot user's Ansoft/Ansys profile state differs substantially
from the owner profile.

Potential experiments:

- Make the workflow or a worker-side wrapper create all required neutral AEDT/HFSS
  profile, ACF, DSO, and temp directories every job, before opening the project.
- Compare the before/after HKCU `Software\Ansoft` export for one job and the next
  job under the same slot account to see whether HTCondor cleanup removes useful
  state.
- Prefer a neutral per-worker or per-job initialization package over copying a
  particular desktop owner's HKCU hive.

Relevant HTCondor mechanism:

- `USER_JOB_WRAPPER` lets an administrator wrap every job on an execute machine.
  On Windows this can be a `.bat`, `.cmd`, `.exe`, or `.com`. It can set environment
  variables or run setup commands before invoking the actual job.

### 5. Submit Environment Should Stay Explicit, But May Need More Ansys State

The running-job environment docs say jobs do not inherit the submit or execute
machine environment by default. The current generated submit file uses
`getenv = False` and an explicit `environment` string, which matches HTCondor's
reproducibility advice.

However, the explicit environment currently focuses on:

- job-local profile/temp paths;
- YADOF HFSS runtime values;
- `ANSYSLMD_LICENSE_FILE`.

The failing solver path may require additional Ansys/HPC variables that are present
for the owner workflow but absent for the slot-user Condor job.

Potential experiments:

1. Capture and diff these environments:
   - direct local owner workflow;
   - tiny Condor slot-user probe;
   - failing HFSS Condor job just before `analyze_setup`.
2. Test a narrow `getenv` matchlist or explicit `environment` additions for only
   Ansys/Python/HPC variables found to be needed. Avoid `getenv=True` as a general
   fix.
3. If the variable should be worker-local rather than submitter-local, consider
   `STARTER_JOB_ENVIRONMENT` or `JOB_INHERITS_STARTER_ENVIRONMENT` at the execute
   host, with a small allowlist.

### 6. Request Shape, Dynamic Slots, And CPU Affinity Need Capturing

`request_cpus` changes the job's requirements and, for partitionable-slot pools,
the size of the dynamic slot carved for the job. HTCondor also writes job and
machine ad files into the scratch directory:

```text
_CONDOR_JOB_AD
_CONDOR_MACHINE_AD
```

The machine ad includes the provisioned slot resources such as `Cpus` and `Memory`.

Potential experiments:

- In every HFSS debug job, copy `_CONDOR_JOB_AD` and `_CONDOR_MACHINE_AD` to a
  returned diagnostics folder.
- Record both `RequestCpus` and actual matched `Cpus`.
- Record process affinity if practical.
- Check `ASSIGN_CPU_AFFINITY` on workers. Its default is false, but if enabled it
  can bind a job to the requested number of cores.

This matters because the follow-up already showed that `request_cpus = 1` with
`YADOF_HFSS_JOB_CPUCORE = 2` changes the solver failure mode.

### 7. Output Transfer Semantics May Hide Diagnostics

The current project pattern intentionally omits `transfer_output_files` so optional
outputs do not hold the job. Official docs say that when this setting is omitted,
HTCondor auto-detects new top-level sandbox files; subdirectory contents are not
part of that default.

For robust HFSS debugging, avoid relying on implicit transfer of nested diagnostics.

Potential experiments:

- Put critical diagnostics at the top level before exit, for example:
  - copied `_CONDOR_JOB_AD`;
  - copied `_CONDOR_MACHINE_AD`;
  - environment dump;
  - solver temp directory listing;
  - ACF file copy;
  - crash-dump/WER path listing.
- Or explicitly transfer directories such as `rawData` and a diagnostics directory,
  but make sure they always exist before exit. If `transfer_output_files` names a
  missing file or directory, HTCondor can put the job on hold.

### 8. Automatic Retry Is Useful For Resources, Not For This Deterministic Crash

HTCondor supports `retry_request_memory`, `retry_request_memory_increase`, and
`max_retries`. These are useful when memory needs are unknown or failures are
transient.

For the current 08 multicore crash, the controlled matrix does not look like a
simple memory request problem. Use these settings for resource calibration and
future automation, not as the primary fix for `hf3d` access violation.

## Suggested Debug Order

1. Confirm the exact Condor runtime environment for a tiny two-core job, especially
   the thread-control variables and `_CONDOR_MACHINE_AD`.
2. Run the 08 two-core job with thread-control variables forced to `1` while
   keeping HFSS cores at `2`.
3. If that fails, test `USE_VISIBLE_DESKTOP=True` on one isolated worker.
4. If that fails, test a worker local group/ACL configuration through
   `DYNAMIC_RUN_ACCOUNT_LOCAL_GROUP`.
5. In parallel, improve returned diagnostics by copying job/machine ads, environment,
   ACF, profile summaries, and temp listings to top-level files.
6. Only after these tests, decide whether the durable fix belongs in:
   - submit-file environment generation;
   - worker HTCondor configuration;
   - per-job AEDT/HFSS initialization;
   - task-level policy that this solver profile stays single-core under Condor.

## Current Best Hypothesis

The most promising new hypothesis is the HTCondor starter's automatic thread
environment. It is Condor-specific, activated by multi-core allocation, and directly
touches native threaded numerical behavior. It also gives a clean experiment that
does not violate the slot-user deployment contract.
