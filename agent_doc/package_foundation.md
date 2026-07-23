# Installation and workspaces

## Install

Install a built wheel into the Python environment used by submit and local worker
processes. Add extras only for features you use:

```powershell
python -m pip install .\dist\yadof-0.1.0-py3-none-any.whl
python -m pip install ".\dist\yadof-0.1.0-py3-none-any.whl[surrogate,plot]"
```

`yadof --version` and `yadof version` report the same package version. Distributed
jobs do **not** carry the yadof package, wheel, source tree, or runtime archive.
HTCondor executes job-local `workflow.py` directly. The assigned parameter snapshot
is self-contained and the package copies only `worker_misc.py` beside the workflow.
Python, NumPy, adapters' third-party dependencies, PyAEDT, and simulator software
still belong to the worker environment.

## Initialize and inspect

```powershell
yadof init D:\work\study-a
yadof check --workspace D:\work\study-a
```

Initialization publishes a generic pure-Python template and `.yadof/workspace.json`
without overwriting existing destinations. Repeating init on the same complete,
version-matched workspace is non-mutating. It does not repair user files or run a
workflow. `check` is read-only: it validates marker/config/task/rawData structure and
discovers backend executables, but never installs or configures software.

## Workspace layout

```text
study-a/
  .yadof/workspace.json
  config.py
  job_template/
    parameters_constraints.py
    workflow.py
    calc_cost.py
    optional adapters and assets
  jobs/                         generated
  recorded_data/                generated raw evidence and metadata
  .yadof/surrogate/checkpoints/ generated
  .yadof/logs/                  generated
  .yadof/tool_output/           generated
```

Relative configured paths resolve from the selected workspace. Two workspaces can
be used consecutively or concurrently in one process without sharing task modules,
records, surrogate state, or output paths. Installed package resources are read-only
inputs and are never used as a runtime-data location.

Prepared distributed jobs contain the task payload, assigned
`parameters_constraints.py`, and `worker_misc.py`. A distributed workflow must not
import yadof; import only same-directory task files, the Python standard library,
and dependencies deliberately installed on execute nodes.

The generic template contains no simulator, vendor, concrete model, or fixed
objective. Use `yadof task adapters` and `yadof task copy-adapter NAME --workspace
PATH` to copy only a selected packaged adapter into user-owned task files.
