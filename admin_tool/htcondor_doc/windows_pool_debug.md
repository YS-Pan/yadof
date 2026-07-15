# Windows HTCondor Pool Debug Guide

## Proven Local Pattern

The verified Windows submit shape for this project is direct workflow submission:

```text
universe = vanilla
executable = workflow.py
transfer_executable = True
getenv = False
load_profile = True
run_as_owner = False
```

The payload is a self-contained job-local `workflow.py`. Python itself is not named
as the HTCondor `executable` in the normal submit file.

## Pool Naming And Network Interface

Set `CONDOR_HOST` to a stable, resolvable DNS name for the central manager. Every
submit and execute node must resolve it. Do not pin `CONDOR_HOST` to a DHCP address
or copy an address discovered on another machine.

Keep `COLLECTOR_HOST = $(CONDOR_HOST):9618` and use `NETWORK_INTERFACE = *` unless
an administrator has a deliberate multi-interface policy. `NETWORK_INTERFACE`
selects a local network interface; it is not the collector hostname. A full Windows
service restart is required after correcting a stale interface binding. The pool
tool implements this policy; see `../htcondor_pool/README.md`.

## Keep Three Questions Separate

Pool health:

- Does `condor_status` show usable slots?
- Does the submit host reach the collector/schedd/startd?
- Are the desired resources advertised?

Runtime identity:

- What does the payload report from `whoami`?
- What does `getpass.getuser()` return?
- Which profile and scratch paths are visible inside the job?

Executable design:

- What command does `job.sub` actually ask HTCondor to start?
- Does the worker know how to execute a transferred `.py` file?
- What does `condor_history` record after completion?

Do not treat a success or failure in one category as proof about the others.

## Identity Notes

For this project, the intended Windows path is slot-user execution:

```text
run_as_owner = False
load_profile = True
```

`run_as_owner=True` is not a production option because the deployment pool consists
of many personal/office workstations with different owners. See
`deployment_contract.md`.

`condor_store_cred` success proves that a credential exists for the account being
queried. It does not prove that a job ran as that account. Runtime identity must be
measured inside the payload.

## Why `load_profile=True` Stays

In the current Windows/PyAEDT environment, `load_profile=False` leaves too little
environment/profile state for robust AEDT startup. A 2026-07-11 probe failed before
solving because Python had no username; after manually adding username variables,
PyAEDT still reported missing AEDT environment discovery and failed before a valid
design object was available.

Keep `load_profile=True` for the slot-user path unless a future worker setup proves
a complete no-profile AEDT startup.

## Sandbox Environment

The submit environment should redirect volatile user paths into the job sandbox:

```text
USERPROFILE=._home
HOME=._home
APPDATA=._appdata
LOCALAPPDATA=._localappdata
TEMP=._tmp
TMP=._tmp
```

The workflow also bootstraps these directories and pins Windows known folders so
AEDT's job-local document paths remain inside the execute sandbox.

## Debugging Order

1. Verify pool roles and slots with `condor_status`.
2. Verify the submit file contains the intended executable, environment, identity,
   resource requests, output/error/log paths, and transfer settings.
3. Submit a tiny payload that writes identity, environment, cwd, and scratch path.
4. Inspect `condor.log` for allocated `Cpus`, `Memory`, slot name, execute scratch,
   and termination reason.
5. Inspect payload stdout/stderr and returned metadata.
6. On a single-machine pool, inspect live files under the worker's configured
   `EXECUTE` directory while the job is still running; HTCondor may remove the
   scratch directory quickly after output transfer.
7. For AEDT/HFSS jobs, preserve `batch.log`, PyAEDT logs, `individual_metadata.json`,
   `job.sub`, `condor.log`, and the copied config snapshot.

## Common Pitfalls

- A transient collector communication error does not always mean the pool is
  globally broken.
- A successful submit is not enough; verify payload-level identity and outputs.
- Direct `.py` execution depends on worker-side associations and ACLs.
- Absolute-interpreter submit files can fail differently across workers and are not
  the current project contract.
- Missing optional output files should not hold jobs; rely on HTCondor's default
  output transfer and job metadata diagnostics.

## Useful Configuration Knobs

- `DAEMON_LIST`
- `CONDOR_HOST`
- `COLLECTOR_HOST`
- `EXECUTE`
- `NUM_CPUS`
- `MEMORY`
- `DISK`
- `STARTER_ALLOW_RUNAS_OWNER`
- `RUN_AS_OWNER`
- `load_profile`
- `run_as_owner`

Owner-execution knobs are listed for diagnosis only; they are not part of the
project's production identity policy.
