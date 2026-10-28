# Windows HTCondor numbered setup scripts

Run the numbered PowerShell scripts by double-clicking them. They relaunch through
Windows UAC with `ExecutionPolicy Bypass`, so no permanent execution-policy change
is required. Keep all five `.ps1` files and `_htcondor_hostname_common.psm1` in the
same directory.

## Order

1. `1_htcondor_leave_all_pools.ps1` stops HTCondor and removes this node's managed
   pool membership.
2. `2_htcondor_register_manager.ps1` asks for the manager name and this machine's
   cluster-LAN adapter name, then enables management and local submission while
   preserving existing execution services and declared resources.
3. `3_htcondor_register_worker.ps1` asks for the manager name and this worker's
   cluster-LAN adapter name, then adds execution without removing an existing
   `SCHEDD`, `COLLECTOR`, or `NEGOTIATOR`.
4. `4_htcondor_set_execute_resources.ps1` asks for the manager name, local
   cluster-LAN adapter, execute directory, CPUs, memory, and disk. Existing values
   are shown as defaults when available. It preserves management and submission
   and adds or updates this node's execute resources.
5. `5_htcondor_enable_submit.ps1` enables local job submission (`SCHEDD`) while
   preserving management, execution, and declared resources. It can also configure
   a submit-only node; registration is checked using the schedd advertisement.

Run script 2 on the manager. Run script 3 on each worker. Run script 4 on every
node that should execute jobs, including the manager when it should also be a
worker.

## Combining roles

These are capability additions, not mutually exclusive role replacements. Existing
services, explicit CPU/memory/disk declarations, execute directory, and flocking
targets survive scripts 2, 3, 4, and 5. Native submit configurations without a
`YADOF_POOL_ROLE` marker are recognized through their effective `DAEMON_LIST`.
Repeated setup merges and deduplicates services instead of removing other roles.

| Intended capabilities | Scripts | Services besides `MASTER` |
| --- | --- | --- |
| Submit only | 5 | `SCHEDD` |
| Execute only | 3, then 4 | `STARTD` |
| Submit and execute | 5 and 3 in either order, then 4 | `SCHEDD`, `STARTD` |
| Manage and submit | 2 | `COLLECTOR`, `NEGOTIATOR`, `SCHEDD` |
| Manage, submit, and execute | 2, then 4; script 3 is optional | `COLLECTOR`, `NEGOTIATOR`, `SCHEDD`, `STARTD` |

All capabilities use the same primary pool. When adding a role, use the same
manager name already configured on that node. A different manager name is rejected
before configuration/service changes; use script 1 first when intentionally
switching pools or removing all roles. Existing `FLOCK_*` settings are preserved
when adding capabilities and cleared by script 1.

`YADOF_POOL_ROLE` remains a primary-role label (`Manager`, `Worker`, or `Submit`),
not a complete capability list. `DAEMON_LIST` shows all enabled services.
Running a role script restarts HTCondor; perform setup during maintenance.
These changes do not automatically recover a role removed by an older script:
run script 5 to restore submission, or script 2 to restore local management.

## Choosing the network adapter

Each machine must select its own adapter connected to the HTCondor cluster LAN.
The script lists local adapters, IPv4 addresses, and descriptions before asking
for the adapter name. Enter the exact value from the `Name` column, such as
`Ethernet`, `Ethernet 2`, or `以太网`. Do not choose an Internet-facing Wi-Fi,
VPN, or unrelated virtual adapter.

The script resolves that friendly name to the local Windows interface GUID and
writes the GUID to `NETWORK_INTERFACE`. The GUID selects a local adapter; it is
not a remote-machine address. `CONDOR_HOST`, `COLLECTOR_HOST`, pool checks, and
authorization continue to use machine names. If a network adapter is replaced or
reinstalled, rerun the relevant role script and select the adapter again.

## Input units

- CPU is the number of logical processors declared to HTCondor.
- Memory is entered in MiB and written to HTCondor `MEMORY`.
- Disk is entered in MiB and converted to KiB for HTCondor `DISK`.
- The execute directory defaults to `R:\condor_execute` when no prior value exists.

Script 4 rejects declarations larger than the detected logical CPU count, physical
memory, or currently free space on the execute drive. It creates the execute
directory and grants the Windows permissions required by HTCondor slot accounts.

## Verification

After a role script completes, it prints the effective configuration. On a
multi-interface node, confirm that `IP_ADDRESS` belongs to the cluster LAN:

```powershell
condor_config_val CONDOR_HOST
condor_config_val NETWORK_INTERFACE
condor_config_val IP_ADDRESS
condor_status -collector -af Name MyAddress
condor_status -af Machine Name MyAddress
```

HTCondor CEDAR addresses display resolved numeric network addresses internally.
That does not mean the scripts configured remote nodes by IP address.

## Offline regression checks

Run from the repository root with the local HTCondor tools available:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    .\admin_tool\htcondor_config\tests\test_offline.ps1 `
    -OutputDirectory .\temp\htcondor-role-regression
```

The checks exercise all role combinations, repeated additions, legacy submit
nodes, resource updates, rejected pool switches, and explicit leave. They use the
real Condor configuration parser on fixture files while replacing service,
firewall, directory-ACL, DNS, and registration operations. Production configuration
hashes, service state, and master process IDs must remain unchanged.
