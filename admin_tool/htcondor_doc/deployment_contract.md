# HTCondor Deployment Contract

## Scope

This contract describes the intended HTCondor deployment shape for this project.
It is not only a local debugging preference; it follows from the application
scenario.

The project and its HTCondor pool are expected to be deployed across many ordinary
office or personal Windows workstations. Those machines are used by different
people, have different interactive owners, and may each act as a submit machine or
an execute machine.

## Identity Policy

The distributed backend must target HTCondor's execute-side slot-user model:

```text
run_as_owner = False
load_profile = True
```

Jobs are expected to run as low-privilege execute-side accounts such as
`condor-slot1_1`, not as the interactive owner of the submit machine.

## Why `run_as_owner=True` Is Excluded

`run_as_owner=True` asks Windows HTCondor to run the job as the submitting user.
That is not compatible with this pool:

- every workstation can be owned by a different person;
- every workstation can be a submit host;
- every execute host would need the ability to run as many possible remote owners;
- maintaining those cross-machine owner credentials and policies is not feasible
  or desirable for office workstations.

Therefore `run_as_owner=True` must not be treated as a production fix path for
distributed evaluation or HFSS debugging in this project.

## Consequences For Debugging

- Reproduce distributed bugs under the slot-user identity rather than under the
  desktop owner.
- Treat owner-mode tests as out-of-policy unless the user explicitly asks for a
  one-off local experiment and accepts that it is not a deployable fix.
- Do not require `condor_credd` / `CREDD_HOST` as a normal YADOF prerequisite.
- Do not design fixes that depend on storing every user's Windows password on every
  possible execute machine.
- If AEDT/HFSS depends on user-profile state, make that state work for the worker
  slot user or job-local sandbox, not for the submitter's owner account.

## Consequences For Submit Files

The current Windows submit pattern remains:

```text
executable = workflow.py
transfer_executable = True
getenv = False
environment = "USERPROFILE=._home HOME=._home APPDATA=._appdata LOCALAPPDATA=._localappdata TEMP=._tmp TMP=._tmp ..."
load_profile = True
run_as_owner = False
transfer_output_files = rawData.zip,individual_metadata.json
```

The environment string may also carry task runtime settings such as
`YADOF_HFSS_JOB_CPUCORE`, `YADOF_HFSS_PARALLEL_TASKS`, and
`ANSYSLMD_LICENSE_FILE`.

## Worker Requirements

Each execute workstation should be configured so its slot users can:

- execute the transferred `workflow.py` path through the machine's Python
  association or configured Windows execution environment;
- read installed Python, PyAEDT, and simulator dependencies;
- write the HTCondor execute scratch directory;
- load enough Windows profile and system environment state for AEDT/PyAEDT startup;
- create and return required job-local `rawData.zip` and
  `individual_metadata.json` through the explicit output list. The zip contains
  direct `.npz` members and HTCondor does not return `rawData/`.

Workers that run HFSS 2024.1 must also exclude `OMP_THREAD_LIMIT` from
`STARTER_NUM_THREADS_ENV_VARS`. Keep the other standard thread variables so they
continue to reflect provisioned CPUs. See `20260713_hfss_fix_experiments.md` for the
validated list and real-job evidence.

## Non-Goals

- Running all jobs as the desktop owner.
- Running a job as a remote submitter's personal Windows account.
- Requiring per-user credential fan-out across all office machines.
- Treating `condor_store_cred` success as proof of the runtime identity.

## Debugging Rule Of Thumb

When a behavior differs between direct local workflow and HTCondor, compare:

1. slot-user identity and profile state;
2. live execute scratch under `C:\condor\execute`;
3. submit environment and resource request;
4. generated job-local files, PyAEDT logs, AEDT `batch.log`, and HTCondor logs.

Do not resolve the difference by switching to owner execution.
