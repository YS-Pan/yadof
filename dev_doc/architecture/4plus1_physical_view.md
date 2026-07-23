# 4+1 physical view

## Submit host

The submit host has the installed yadof environment, one or more writable
workspaces, and HTCondor client tools when distributed mode is used. Workspace
`jobs/` is submit-side staging and must never point at an execute node's scratch
directory. Local evaluation uses the installed environment to launch job-local
`workflow.py` files.

## Prepared job contents

Every job places required task inputs directly below its own directory (including
task-owned subdirectories when necessary). Framework composition adds only
`worker_misc.py`; assigned `parameters_constraints.py` is self-contained. No yadof
package directory, wheel, zip archive, compatibility bootstrap, generated worker
config, copied global config package, or `calc_cost.py` is sent to execute nodes.
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
directories or old outputs. The execute workflow creates `rawData.zip`; its archive
members are direct `.npz` files such as `response.npz`, never
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

- `jobs/<job>/metadata.json`: submit-side aggregate job state and diagnostics.
- `jobs/<job>/individual_metadata.json`: workflow-owned lifecycle state.
- `jobs/<job>/rawData.zip`: distributed transport artifact.
- `jobs/<job>/rawData/*.npz`: restored/direct evidence used by framework code.
- `recorded_data/indMeta.jsonl`: compact append-only individual records.
- `recorded_data/rawData.npz`: zip-based durable evidence archive, namespaced by job.
- configured checkpoint/log/tool-output directories: workspace-local mutable state.

JSON and archive publication requiring replacement is atomic and protected by
workspace locks. Package resources remain read-only even when site-packages itself
is read-only.
