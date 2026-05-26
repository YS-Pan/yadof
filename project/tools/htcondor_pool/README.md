# HTCondor pool setup scripts

Run these scripts on the physical machines, in this order:

1. On machine 1: `setup_machine_1_manager.cmd`
2. On machine 3: `setup_machine_3_worker.cmd`
3. On machine 6: `setup_machine_6_worker.cmd`

Do not pass command-line arguments. Machine 1 automatically detects its own
LAN IP and writes it to `manager_ip.txt` in this folder. Machine 3 and 6 read
that file automatically when they join the pool. If the folder is copied instead
of shared, run machine 1 first, then copy the updated folder including
`manager_ip.txt` to machine 3 and 6.

Each `.cmd` requests Administrator privileges, detects the local IPv4 address,
writes an HTCondor local config block, opens Windows Firewall TCP port `9618`
for the detected local subnet, and restarts HTCondor. If no HTCondor Windows
service is registered, the setup script starts `condor_master.exe` directly from
the detected `bin` directory. Re-running a worker script after a mistaken
manager setup overwrites the managed config block and restarts local HTCondor
processes from the detected `bin` directory.

The scripts do not require HTCondor to be in `PATH`. They search `D:\condor\bin`
by default, plus common install locations such as `C:\Condor\bin`,
`C:\Program Files\HTCondor\bin`, and the Windows service path. If HTCondor has
no `LOCAL_CONFIG_FILE`, the setup script writes `D:\condor\condor_config.local`
and makes `D:\condor\condor_config` load it. For a custom install directory, set
`CONDOR_LOCATION` to the HTCondor root before running the `.cmd`.

If you want to add HTCondor to the system `PATH` first, run:

```cmd
add_condor_to_path.cmd
```

For a custom install root:

```cmd
add_condor_to_path.cmd "D:\HTCondor"
```

The worker scripts first read `manager_ip.txt`. If that file is missing or
points to an unreachable host, they fall back to scanning the local subnet for
an HTCondor collector on port `9618`.

After all three finish, verify from machine 1:

```cmd
show_slots.cmd
condor_status
condor_status -af Name Machine Cpus Memory OpSys
```

If machine 1 only shows one slot, run `diagnose_pool.cmd` on machine 3 and 6.
Check that `manager_ip.txt` exists, `Test-NetConnection` to machine 1 port
`9618` succeeds, `DAEMON_LIST` is `MASTER, SHARED_PORT, STARTD`, and local
`condor_*.exe` processes are running.

## Adding more worker machines

To add another machine to the same HTCondor pool later:

1. Install HTCondor on the new machine under `D:\condor`.
2. Copy this whole `htcondor_pool` folder to the new machine.
3. Make sure the copied folder contains the current `manager_ip.txt` generated
   by machine 1. If machine 1's IP changed, re-run `setup_machine_1_manager.cmd`
   on machine 1 first, then copy the new `manager_ip.txt`.
4. Run a worker setup script on the new machine. You can reuse
   `setup_machine_3_worker.cmd`; the machine label is only a local marker and
   does not affect HTCondor matching. If you want a clearer label, copy
   `setup_machine_3_worker.cmd` to a new name such as
   `setup_machine_7_worker.cmd` and change both `-MachineLabel 3` occurrences
   inside it to `-MachineLabel 7`.
5. Verify from machine 1 with `show_slots.cmd`. The new machine should appear
   as another `slot1@...` row.

Only machine 1 should run `setup_machine_1_manager.cmd`. Every additional
machine should run a worker script. The new machine must be able to reach
machine 1 on TCP port `9618`.

Re-run the matching script if a machine receives a new IP address.
