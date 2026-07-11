# HFSS Condor Multicore Debug Notes 2026-07-11

## Scope

This file records the live debugging pass for the Condor-specific HFSS multicore
failure described in `reference/hfss_condor_multicore_diagnosis_reference.md`.
It focuses on changes or tests made after that reference was written.

## Starting Evidence

- Direct local workflow can solve the 08 Mixed Order plus Iterative Solver project
  with `YADOF_HFSS_JOB_CPUCORE=6`.
- HTCondor workflow runs of the same 08 project fail when HFSS uses more than one
  core.
- The 09 Direct Solver control is not the failing case.
- The user changed `.aedt` and some `job_template` files lightly; this pass did
  not repeat the full original matrix.

## Experiments This Pass

### Current direct-`workflow.py` submit still fails

The original diagnosis included failing Condor jobs that used an older submit file
shape:

```text
executable = C:\PROGRA~1\PYTHON~1\python.exe
arguments = workflow.py
transfer_executable = False
```

The current code now submits the job-local workflow directly:

```text
executable = workflow.py
transfer_executable = True
```

A new minimal 08/2-core/16GB Condor run was submitted as cluster `4218` on
2026-07-11. It still failed in the same way:

- runtime identity: `desktop-derg5ld\condor-slot1_1`
- Condor scratch: `C:\condor\execute\dir_2368\scratch`
- Condor return value: `1`
- workflow error: `analyze_setup returned False for 'Setup1'`
- AEDT batch log: `process hf3d exited with code -1073741819`

Conclusion: the failure is not caused by the earlier Python-as-executable submit
shape.

### `run_as_owner=True` is blocked by local HTCondor configuration

A temporary owner-mode submit was generated with:

```text
load_profile = False
run_as_owner = True
```

`condor_submit` failed before the job entered the queue:

```text
ERROR: run_as_owner requires a valid CREDD_HOST configuration macro
```

Relevant local configuration observations:

- `condor_config_val DAEMON_LIST` returns `MASTER COLLECTOR NEGOTIATOR SCHEDD STARTD`.
- `CREDD_HOST` is not defined.
- `SEC_CREDENTIAL_DIRECTORY` is not defined.
- `C:\condor\condor_config.local` contains:

```text
STARTER_ALLOW_RUNAS_OWNER = False
RUN_AS_OWNER = False
```

`condor_store_cred query` reports that `ysPan@DESKTOP-DERG5LD` has a valid stored
password credential. The missing piece for this test is the HTCondor service-side
`condor_credd` / `CREDD_HOST` / starter policy configuration, not the submit file.

Conclusion: owner-mode is the most direct way to test the user/session hypothesis,
but it requires explicit service-level HTCondor configuration.

This was rechecked after the later variants. The machine still reports:

- `DAEMON_LIST = MASTER COLLECTOR NEGOTIATOR SCHEDD STARTD`
- `CREDD_HOST`: not defined
- `SEC_CREDENTIAL_DIRECTORY`: not defined
- `STARTER_ALLOW_RUNAS_OWNER = False`
- `RUN_AS_OWNER = False`
- `CREDD_CACHE_LOCALLY = false`
- `condor_store_cred query`: `ysPan@DESKTOP-DERG5LD` has a valid stored password
  credential

### Disabling PyAEDT DSO distribution types did not fix the crash

As a conservative source-side probe, `hfss_com.analyze()` was temporarily changed
to pass `allowed_distribution_types=[]` into PyAEDT `analyze_setup()`, while still
requesting two cores. A new 08/2-core/16GB Condor run was submitted as cluster
`4220`.

The job still failed in the same way:

- runtime identity: `desktop-derg5ld\condor-slot1_1`
- `runtime_hfss_allowed_distribution_types`: `[]`
- workflow error: `analyze_setup returned False for 'Setup1'`
- AEDT batch log: `process hf3d exited with code -1073741819`

The temporary source change was reverted because it did not solve the failure.

Conclusion: simply disabling DSO distribution types through PyAEDT's generated ACF
is not sufficient.

### Owner profile and slot profile differ substantially

A non-solving inventory probe compared the interactive owner context with the Condor
slot context.

Owner context:

- `whoami`: `desktop-derg5ld\yspan`
- `USERPROFILE`: `C:\Users\ysPan`
- `APPDATA`: `C:\Users\ysPan\AppData\Roaming`
- `LOCALAPPDATA`: `C:\Users\ysPan\AppData\Local`
- `HKCU\Software\Ansoft` export: 444 lines, 72 registry keys
- `C:\Users\ysPan\Documents\Ansoft` exists and already contains AEDT libraries,
  results, `.pyaedt` state, `PersonalLib`, and temp content.
- `C:\Users\ysPan\AppData\Roaming\Ansys` and
  `C:\Users\ysPan\AppData\Local\Ansys` exist.

Condor slot context:

- `whoami`: `desktop-derg5ld\condor-slot1_1`
- real loaded profile: `C:\Users\condor-slot1_1.DESKTOP-DERG5LD`
- real `APPDATA`: `C:\Users\condor-slot1_1.DESKTOP-DERG5LD\AppData\Roaming`
- real `LOCALAPPDATA`: `C:\Users\condor-slot1_1.DESKTOP-DERG5LD\AppData\Local`
- real `TEMP`: `C:\Users\CONDOR~1.DES\AppData\Local\Temp`
- `HKCU\Software\Ansoft` export: 25 lines, 8 registry keys
- the slot user's `Documents\Ansoft`, `AppData\Roaming\Ansys`, and
  `AppData\Local\Ansys` are absent before the normal job-local bootstrap.

This matters because the successful direct local workflow also uses job-local
`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, and `TEMP`, but it still starts AEDT under
the owner's loaded HKCU registry hive. The failing Condor workflow starts AEDT under
the much thinner slot-user HKCU hive. That narrows the likely difference from
"job-local profile paths" to the Windows account/session/registry context that owns
the AEDT process.

Both the successful direct local job and the failing Condor job print the AEDT
"new installation" library reset message, so that message is not by itself the
failure trigger.

### DSO startup probe

A no-solve Condor probe started AEDT under `condor-slot1_1`, opened the same project,
set variables, and called PyAEDT `set_custom_hpc_options(cores=2, tasks=1,
use_auto_settings=False)` without calling `Analyze`.

Results from cluster `4223`:

- status: done
- runtime identity: `desktop-derg5ld\condor-slot1_1`
- scratch: `C:\condor\execute\dir_7700\scratch`
- `active_dso_before`: empty string
- `active_dso_after`: `pyaedt_config`
- `set_custom_hpc_options_ok`: true
- returned `probe_outputs.zip` containing the generated `pyaedt_config.acf`

The generated ACF contains:

```text
ConfigName='pyaedt_config'
DesignType='HFSS'
MachineName='localhost'
NumEngines=1
NumCores=2
UseAutoSettings=False
AllowedDistributionTypes[9: 'Variations', 'Frequencies', 'Mesh Assembly','Mesher', 'Transient Excitations', 'Domain Solver', 'Solver', 'Iterative Solver', 'Direct Solver']
BoolValues(AllowOffCore=true)
```

This shows that the slot user can start AEDT and can apply the PyAEDT DSO/HPC
configuration. The crash happens later, inside `hf3d`, not while creating the
`pyaedt_config` registry/config state.

### `use_auto_settings=True` did not fix the solve

A temporary job-copy-only variant changed the copied `hfss_com.py` from
`use_auto_settings=False` to `use_auto_settings=True` and reran the smallest failing
case as cluster `4224`.

The job still failed:

- runtime identity: `desktop-derg5ld\condor-slot1_1`
- scratch: `C:\condor\execute\dir_35644\scratch`
- workflow error: `analyze_setup returned False for 'Setup1'`
- AEDT batch log: `process hf3d exited with code -1073741819`

Conclusion: allowing AEDT/PyAEDT automatic DSO settings is not enough to avoid the
slot-user multicore crash.

### Using the slot user's real profile did not fix the solve

A temporary job-copy-only variant removed the job-local profile bootstrap and removed
`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, and `TMP` from the Condor submit
environment, while keeping the 08/2-core HFSS settings.

Cluster `4225` still failed:

- runtime identity: `desktop-derg5ld\condor-slot1_1`
- runtime `USERPROFILE`: `C:\Users\condor-slot1_1.DESKTOP-DERG5LD`
- runtime `APPDATA`: `C:\Users\condor-slot1_1.DESKTOP-DERG5LD\AppData\Roaming`
- runtime `LOCALAPPDATA`: `C:\Users\condor-slot1_1.DESKTOP-DERG5LD\AppData\Local`
- runtime `TEMP`: `C:\Users\CONDOR~1.DES\AppData\Local\Temp`
- AEDT batch project directory:
  `C:\Users\condor-slot1_1.DESKTOP-DERG5LD\Documents\Ansoft`
- workflow error: `analyze_setup returned False for 'Setup1'`
- AEDT batch log: `process hf3d exited with code -1073741819`

Conclusion: scratch-local profile redirection is not necessary for the failure.
The common failing condition is still the Condor slot-user execution context.

### `request_cpus=1` with HFSS two-core solve changed the failure, but did not fix it

A temporary job-copy-only variant changed only the Condor resource request:

```text
request_cpus = 1
YADOF_HFSS_JOB_CPUCORE = 2
```

Cluster `4226` still failed under `desktop-derg5ld\condor-slot1_1`. The Condor log
confirmed the allocation:

```text
Cpus = 1
Memory = 16384
```

The failure changed from the usual access-violation-like `hf3d` exit
`-1073741819` to an HFSS matrix solver out-of-memory message:

```text
process hf3d error: Matrix solver exception: SOLVER_OUT_OF_MEMORY
process hf3d: Out of memory
```

Conclusion: Condor CPU allocation affects the HFSS solver path, but under-requesting
CPUs while asking HFSS for two cores is not a valid workaround.

### `load_profile=False` is not a viable slot-user fix in the current environment

A temporary job-copy-only variant changed:

```text
load_profile = False
run_as_owner = False
```

Cluster `4227` failed before starting AEDT because the no-profile environment did
not contain a username for Python `getpass.getuser()`:

```text
OSError: No username set in the environment
```

A follow-up variant added `USERNAME`, `USER`, and `LOGNAME` while keeping
`load_profile=False`. Cluster `4228` got slightly farther but still failed before
the solve:

```text
UserWarning: No installed versions of AEDT are found in the system environment variables
AttributeError: 'Hfss' object has no attribute '_odesign'
```

Conclusion: in this local HTCondor installation, the slot-user path needs
`load_profile=True` to provide a usable AEDT/PyAEDT runtime environment. Turning it
off is not a fix.

### Local single-machine Condor observation note

This machine runs HTCondor collector, submit, and execute roles locally. Therefore,
while a job is running, the live execute sandbox can be inspected directly under
`C:\condor\execute`. This is useful for observing transient AEDT/PyAEDT files that
may not be transferred back after job exit.

## Current Working Interpretation

The strongest remaining hypothesis is that the 08 Mixed Order plus Iterative Solver
multicore solve is unstable under the HTCondor slot-user Windows context. The same
workflow and project can run under the desktop user, and the same Condor slot-user
path can run less sensitive controls.

The next decisive test is a real Condor run under the submitting desktop user
(`run_as_owner=True`) with `load_profile=False`, while preserving job-local
`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, and `TMP`.

## Open Safety Gate

Enabling that test requires persistent HTCondor service configuration, including
`condor_credd` and `STARTER_ALLOW_RUNAS_OWNER=True`. This changes how the local
Condor service may run jobs and should only be done with explicit user approval.
