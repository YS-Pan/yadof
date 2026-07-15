# HTCondor pool-node tool

`htcondor_pool.ps1` is the only setup and diagnostic tool in this folder.  One
`Configure` invocation writes the node role, firewall rule, execute directory,
resource declaration, slot layout, optional Python ACL, and optional starter-thread
override into one managed HTCondor configuration block, then performs one full
HTCondor restart.

Run it from an elevated Administrator PowerShell session on each node.  It finds
HTCondor from `PATH`, `CONDOR_LOCATION`, normal Program Files locations, or its
Windows service.  For a custom installation, pass `-CondorLocation <install-root>`.
It does not persist `PATH` or create system environment variables. If HTCondor was
installed without a Windows service, it starts the discovered `condor_master.exe`
directly after writing the configuration.

## Before configuring nodes

Choose a stable, resolvable name for the central manager, preferably a LAN DNS
record such as `condor-collector.example.local`.  Every submit and execute node
must resolve this name to the manager's current address.  In a network without DNS,
use a consistent hosts mapping or DHCP address reservation on every node.

`CONDOR_HOST` is the manager's reachable name.  It is not a local interface
selection.  The tool writes `NETWORK_INTERFACE = *` by default so HTCondor follows
active interfaces instead of retaining a DHCP address.  Do not put the manager
hostname into `NETWORK_INTERFACE`.  See
[`temp/HTCondor_collector_主机名网络配置总结.md`](../../temp/HTCondor_collector_主机名网络配置总结.md)
for the reasoning and verification commands.

The firewall and HTCondor allow scope are derived from the route-selected IPv4
network by default.  On a multi-network machine, pass `-AllowedNetwork` and, when
needed, `-AllowedHostPattern` explicitly.  `-AdvertiseAddress` only selects the
local address used to derive those defaults; it is never written into
`NETWORK_INTERFACE`.

## Configure the manager

A manager that only schedules and submits jobs needs no resource arguments:

```powershell
.\htcondor_pool.ps1 -Action Configure -Role Manager `
    -ManagerHost condor-collector.example.local
```

If that same computer should execute jobs, add `-EnableExecute` and declare the
capacity that HTCondor may allocate.  `DeclaredMemoryMb` and `DeclaredDiskMb` are
MB; disk capacity must fit in the selected execute directory.

```powershell
.\htcondor_pool.ps1 -Action Configure -Role Manager `
    -ManagerHost condor-collector.example.local `
    -EnableExecute `
    -DeclaredCpus 8 `
    -DeclaredMemoryMb 24576 `
    -DeclaredDiskMb 51200 `
    -ExecuteDir 'E:\htcondor_execute' `
    -PythonExecutable 'C:\Python311\python.exe'
```

## Configure each worker

Run one command per execute machine.  Use the same manager name and choose the
resource values and scratch location for that particular machine.

```powershell
.\htcondor_pool.ps1 -Action Configure -Role Worker `
    -ManagerHost condor-collector.example.local `
    -DeclaredCpus 8 `
    -DeclaredMemoryMb 24576 `
    -DeclaredDiskMb 51200 `
    -ExecuteDir 'E:\htcondor_execute' `
    -PythonExecutable 'C:\Python311\python.exe'
```

Execute nodes use one partitionable slot.  HTCondor carves dynamic slots from the
declared CPU, memory, and disk capacity as jobs request resources.  The tool also
advertises `YADOF_EXECUTE_READY`, `YADOF_EXECUTE_DIR`, and the declared capacities;
these are descriptive worker attributes, not submit-side job paths.

`JOBS_DIR` in the yadof project remains the submit-side staging location.  It must
not be repointed at a worker's `EXECUTE` directory.

## Optional starter-thread override

Do not add simulator-specific policy to every pool by default.  If a validated
workload requires excluding a starter-injected thread variable, request that exact
exclusion when configuring the affected execute node:

```powershell
.\htcondor_pool.ps1 -Action Configure -Role Worker `
    -ManagerHost condor-collector.example.local `
    -DeclaredCpus 8 -DeclaredMemoryMb 24576 -DeclaredDiskMb 51200 `
    -ExecuteDir 'E:\htcondor_execute' `
    -ExcludeStarterThreadVariable OMP_THREAD_LIMIT
```

The tool reads the installed HTCondor list and removes only the requested names; it
does not embed a version-specific default list.  If the effective list cannot be
read, pass the approved baseline with one or more `-StarterThreadVariable` values.
Repeat the exclusion whenever the managed node configuration is reapplied.  Verify
the actual value after every HTCondor upgrade:

```powershell
condor_config_val STARTER_NUM_THREADS_ENV_VARS
```

## Inspect and troubleshoot

The diagnostic mode is read-only and can run without elevation.  It prints the
effective configuration and queries the visible slots using either the supplied
manager name or the configured `CONDOR_HOST`.

```powershell
.\htcondor_pool.ps1 -Action Diagnose `
    -ManagerHost condor-collector.example.local
```

For a safe review of the configuration that would be written, add `-DryRun` to a
`Configure` command.  `-VerificationTimeoutSec 0` skips only the post-restart
collector wait; it does not skip configuration verification output.

## Deployment contract

This tool configures the HTCondor environment only.  Yadof distributed jobs retain
their Windows slot-user contract:

```text
run_as_owner = False
load_profile = True
```

Do not use owner execution as a general cluster repair path.  See
[`../htcondor_doc/deployment_contract.md`](../htcondor_doc/deployment_contract.md)
and [`../htcondor_doc/windows_pool_debug.md`](../htcondor_doc/windows_pool_debug.md)
for the deployment and debugging policy.
