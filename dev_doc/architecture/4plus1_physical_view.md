# 4+1 physical view

## Submit host

The submit host has the installed yadof environment, one or more writable
workspaces, and HTCondor client tools when distributed mode is used. Workspace
`jobs/` is submit-side staging and must never point at an execute node's scratch
directory. Local evaluation uses the installed environment to launch job-local
`workflow.py` files.

Local planning reads the submit host's physical/logical CPU counts, currently
available memory, and free space on the jobs volume through the core psutil
dependency. A configured reserve fraction protects host headroom. These snapshots
are ephemeral planning inputs; durable records contain only the chosen plan and
per-job process-tree measurements.

## External PyChrono runtime

`YADOF_PYCHRONO_PYTHON` names one absolute, administrator-provisioned interpreter
file on the machine that executes the task. Yadof does not activate its Conda
environment, use PATH to select it, mutate the parent/user/machine PATH, import
PyChrono, or install itself into that environment. On Windows, the adapter prepends
the selected prefix's standard Conda DLL directories only to each child environment
copy. The shared prefix is read-only and contains no candidate data, cache,
bytecode, or log output. A matching absolute string on another execute host is not
proof that the runtime exists or is accessible there.

Every PyChrono invocation has a distinct writable candidate scratch holding only
its request, result, temporary content, and child rawData. The child working
directory and TEMP/TMP point there, inherited PYTHONPATH is absent, and user-site
and bytecode writes are disabled. Local/distributed publication moves only fully
validated direct NPZ files into the prepared job's final rawData; fast publication
copies their arrays into memory before deleting scratch.

Fast planning uses its own configured worker cap and declared CPU, memory, and
scratch-disk requirement per worker; it does not reinterpret HTCondor requests.
Reusable fast workers run only on this host. Each active candidate may own one
temporary scratch directory below `FAST_EVALUATION_SCRATCH_DIR` (default
`.yadof/fast_scratch`), never below `jobs/` or `recorded_data/`. Scratch carries no
job, evidence, or recovery semantics and is removed after success, error, timeout,
or crash cleanup. A pure/API task may leave it physically unused.

## Prepared job contents

Every job places required task inputs directly below its own directory (including
task-owned subdirectories when necessary). Framework composition adds only
`worker_misc.py`; it owns invariant execute-side paths, lifecycle metadata,
execute-machine provenance, rawData preparation, and flat output transport.
Assigned `parameters_constraints.py` is self-contained. No yadof
package directory, wheel, zip archive, compatibility bootstrap, generated worker
config, copied global config package, or `calc_cost.py` is sent to execute nodes.
Direct `job_template/` children ending case-insensitively with `.aedtresults` or
`.aedt.lock` are excluded before copying; the rule deliberately does not inspect
task-owned subdirectories.
The job static hash covers task/support definitions while ignoring runtime metadata
and candidate assignment values.

## HTCondor transport

The Windows submit contract is:

```text
universe = vanilla
executable = workflow.py
transfer_executable = True
getenv = False
load_profile = True
run_as_owner = False
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_output_files = rawData.zip,individual_metadata.json
```

`workflow.py` and other task inputs are already in the prepared job folder. Condor
transfers the executable plus selected direct inputs, and does not transfer runtime
directories or old outputs. Package worker support invoked by the execute workflow
creates `rawData.zip`; its archive members are direct `.npz` files such as
`response.npz`, never
`rawData/response.npz`. Condor returns the zip instead of the `rawData/` directory.
The submit host restores validated files into its job-local `rawData/`.

Worker Python and installed third-party software provide task dependencies such as
NumPy, PyAEDT, and HFSS. They do not need yadof importability. Consequently a
distributed task workflow may import only job-local files, Python standard library,
and dependencies deliberately installed on workers.

Windows execution uses low-privilege slot users with `run_as_owner = False` and
`load_profile = True`. Per-job sandbox home/temp directories are transferred inputs.
HTCondor deployment, permissions, credentials, licensing, and machine policy remain
under the administrator boundary in `admin_tool/` documentation.

The redirected environment uses job-local home/appdata/temp names. The workflow
creates runtime directories before starting external software. Worker scratch
placement and capacity are configured and advertised by administrators, never by a
workspace path setting.

## Durable workspace layout

- user-created task/debug/export directories may coexist with the reserved layout;
  core workspace discovery/checking ignores them unless configuration or task code
  explicitly references them, and they are not implicit prepared-job payload;
- `jobs/<job>/metadata.json`: submit-side aggregate job state and diagnostics.
- `jobs/<job>/individual_metadata.json`: workflow-owned lifecycle state.
- `jobs/<job>/rawData.zip`: distributed transport artifact.
- `jobs/<job>/rawData/*.npz`: restored/direct evidence used by framework code.
- fast logical evaluations have none of the `jobs/<job>/...` paths above; named
  memory payloads enter `recorded_data/rawData.npz` directly through the recorder.
- `recorded_data/indMeta.jsonl`: compact append-only individual records.
- `recorded_data/rawData.npz`: zip-based durable evidence archive, namespaced by job.
- configured checkpoint/log/tool-output directories: workspace-local mutable state.

JSON and archive publication requiring replacement is atomic and protected by
workspace locks. Package resources remain read-only even when site-packages itself
is read-only.

The wheel also carries `yadof/tools/surrogate_viewer/`, including its independent
developer-documentation subtree. Its Torch and Matplotlib dependencies are exposed
through the `viewer` extra and are used only on the submit/user desktop. Viewer code
and dependencies are never copied into a prepared job or transferred to execute
nodes.

The task workflow calls package worker support, which samples `execute_machine` in
the workflow process and writes it into `individual_metadata.json`. It is
transferred back with normal job outputs and remains authoritative. If timeout
prevents that transfer, the submit host may persist a separate
`condor_execute_machine` fallback parsed from the job-local `condor.log`, together
with its slot and `condor_user_log` source. Submit-side ClassAds do not override
either provenance path.
