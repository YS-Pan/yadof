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

## Worker R: execute directory

To make HTCondor execute-side scratch folders run on each worker machine's
`R:` RAM disk, run this file on every machine that has a startd slot:

```cmd
setup_worker_ramdisk_execute.cmd
```

For the current three-machine pool, run it on machine 1, machine 3, and machine
6. Machine 1 is both submit/manager and worker, so it also needs this step.

The script requests Administrator privileges, creates `R:\condor_execute`,
grants access to system, administrators, and authenticated slot users, writes a
managed HTCondor config block with:

```text
EXECUTE = R:/condor_execute
YADOF_RAMDISK = True
YADOF_EXECUTE_DIR = "R:/condor_execute"
STARTD_ATTRS = YADOF_RAMDISK, YADOF_EXECUTE_DIR
```

Then it restarts HTCondor and prints `condor_config_val`/`condor_status`
verification output. The script is safe to re-run; it replaces only its managed
`# BEGIN YADOF RAMDISK EXECUTE` block.

Do not set `project/config.py` `JOBS_DIR` to `R:\` for this purpose. `JOBS_DIR`
is the submit-side job staging directory. Worker-side RAM-disk execution is
controlled by HTCondor `EXECUTE` on each worker, and optimization jobs can match
those workers with `TARGET.YADOF_RAMDISK =?= True`.

Run this after the pool role setup scripts, and make sure the `R:` RAM disk
exists before starting HTCondor. If `R:` is recreated after reboot, recreate it
before the HTCondor service starts or re-run this script.

If machine 1 only shows one slot, run `diagnose_pool.cmd` on machine 3 and 6.
Check that `manager_ip.txt` exists, `Test-NetConnection` to machine 1 port
`9618` succeeds, `DAEMON_LIST` is `MASTER, SHARED_PORT, STARTD`, and local
`condor_*.exe` processes are running.

## Worker declared resources and multi-job slots

To control how many resources each worker advertises and allow one machine to
run multiple jobs, edit the constants at the top of:

```cmd
setup_worker_declared_resources.cmd
```

Then run it on each execute-capable machine, including machine 1 if it should
also run HFSS jobs. The key constants are:

```cmd
set "DECLARE_CPUS=6"
set "DECLARE_MEMORY_MB=24576"
set "DECLARE_DISK_MB=8192"
set "EXECUTE_DIR=R:\condor_execute"
set "WORKER_PYTHON_EXE=C:\ProgramData\miniconda3\envs\yadof\python.exe"
set "PARTITIONABLE_SLOT=1"
```

`DECLARE_MEMORY_MB` is MB. `DECLARE_DISK_MB` is MB and should not exceed the
usable size of the `R:` RAM disk. With `PARTITIONABLE_SLOT=1`, HTCondor creates
one partitionable worker slot that can be split into multiple dynamic slots as
jobs request CPU, memory, and disk.

`WORKER_PYTHON_EXE` should match `project/config.py` `HTCONDOR_PYTHON_EXE`.
The script grants read/execute access on that Python environment to
Authenticated Users and Users, which avoids Windows worker holds such as
`Permission denied` while executing `python.exe`.

For example, if a worker declares 6 CPUs and 24576 MB memory, and each job
requests 2 CPUs and 4096 MB memory in `project/config.py`, that worker can run
up to three jobs before another resource becomes the limiting factor.

After running the script, verify from machine 1:

```cmd
condor_status -af Name Machine Cpus Memory Disk State Activity YADOF_RAMDISK YADOF_DECLARED_CPUS YADOF_DECLARED_MEMORY_MB
```

If a worker shows `MEMORY` or `DISK` as not defined, or shows `0` in
`condor_status`, run `setup_worker_declared_resources.cmd` on that worker.

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
