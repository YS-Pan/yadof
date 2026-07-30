# Installation and workspaces

## AI agent prerequisite

yadof is intended to be used through an AI coding agent. Install an agent before
authoring a task, then open the selected writable workspace in that agent. OpenAI
Codex is recommended because the author used it for development and verification.
The agent should begin with `yadof docs show user README.md` and follow the
version-matched reading order before it edits anything.

## Install

Install a built wheel into the Python environment used by submit and local worker
processes. Add extras only for features you use:

```powershell
python -m pip install .\dist\yadof-0.2.0-py3-none-any.whl
python -m pip install ".\dist\yadof-0.2.0-py3-none-any.whl[surrogate,plot]"
python -m pip install ".\dist\yadof-0.2.0-py3-none-any.whl[viewer]"
```

`yadof --version` and `yadof version` report the same package version. Distributed
jobs do **not** carry the yadof package, wheel, source tree, or runtime archive.
HTCondor executes job-local `workflow.py` directly. The assigned parameter snapshot
is self-contained and the package copies only `worker_misc.py` beside the workflow.
That helper owns behavior invariant across tasks: standard paths, execute identity,
lifecycle/error metadata, rawData preparation, and flat output transport. Python,
NumPy, adapters' third-party dependencies, PyAEDT, and simulator software still
belong to the worker environment.

The `viewer` extra installs the Torch and Matplotlib dependencies needed by
`yadof view surrogate`; Tkinter must also be available in the selected Python
installation. The viewer is submit-side, read-only inspection software and is
never copied into distributed jobs.

Version `0.1.0` identifies the older pre-package project. Version `0.2.0`
identifies the current installable-package line.

The reference development machine used Windows 11 Pro 25H2, ANSYS Electronics
Desktop 2024 R1, CPython 3.13.11, PyAEDT 0.24.1, NumPy 2.2.6, pymoo 0.6.2, and
psutil 7.2.2, and HTCondor 25.4.0. psutil is a core dependency because local
resource planning measures the workflow and simulator process tree. This is a
reproducibility snapshot rather than a minimum-version contract; the wheel metadata
remains authoritative for Python and dependency requirements.

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
`parameters_constraints.py`, and `worker_misc.py`. Direct `job_template/` children
ending with `.aedtresults` or `.aedt.lock` are excluded as AEDT runtime artifacts;
the suffix rule does not inspect nested task directories. A distributed workflow
must not import yadof; import only same-directory task files, the Python standard
library, and dependencies deliberately installed on execute nodes.

Workspace `workflow.py` and `calc_cost.py` contain only behavior that can change
with the optimization task. They call copied `worker_misc` or installed
`yadof.job_template` helpers for every cross-task invariant.

The generic template contains no simulator, vendor, concrete model, or fixed
objective. Use `yadof task adapters` and `yadof task copy-adapter NAME --workspace
PATH` to copy only a selected packaged adapter into user-owned task files.
