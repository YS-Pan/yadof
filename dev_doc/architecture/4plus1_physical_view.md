# 4+1 physical view

The submit host has an installed yadof environment and writable workspaces. Local
workers use that environment. HTCondor jobs transfer the workspace task payload,
assigned parameters, `worker_misc.py`, `sitecustomize.py`, and compact worker config.
The slot's Python environment must provide the same yadof version; bootstrap records
missing/incompatible runtime diagnostics before task execution.

Windows execution uses low-privilege slot users with `run_as_owner = False` and
`load_profile = True`. Per-job sandbox home/temp directories are transferred inputs.
HTCondor deployment, permissions, credentials, licensing, and machine policy remain
under the administrator boundary in `admin_tool/` documentation.
