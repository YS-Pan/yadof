# Installed Package And Workspace Foundation

Yadof now has an installable package foundation named `yadof`. The distribution,
Python import, and console command use the same name, and the current version is
reported from one package source.

## Install For The Current Stage

From a source checkout, a standard PEP 517 frontend can install the package:

```powershell
python -m pip install .
```

Development and artifact checks use the `dev` extra:

```powershell
python -m pip install ".[dev]"
```

The optional dependency layers are:

- `surrogate`: PyTorch surrogate training and prediction.
- `plot`: result plotting.
- `hfss`: the optional HFSS adapter's Python dependency.
- `dev`: package build, test, and artifact-check tools.

HTCondor executables, simulator applications, and machine configuration are still
prepared by an administrator and are not pip dependencies.

## Available Installed Commands

This foundation stage deliberately exposes only commands that do not need a task
workspace or the not-yet-migrated runtime:

```powershell
yadof --help
yadof --version
yadof version
yadof docs user
yadof docs dev
```

The document commands print UTF-8 entry content. They do not open a GUI and do not
write into the installed package.

## Current Transition Boundary

Optimization, evaluation, history, surrogate, and user-tool runtime modules still
live under `project/`. Continue using the source-tree workflow in
`optimization_workflow.md` and `config_and_run.md` until their ordered package
migration steps replace those entry points.

The package foundation does not provide a `project.*` compatibility alias and does
not yet implement `yadof init`, `check`, `smoke-test`, `run`, history, view, or task
commands. Their absence is intentional rather than an installation error.

## Available Workspace Python APIs

The installed package can already represent and validate the package-era workspace
boundary without creating runtime state:

```python
from yadof import WorkspaceContext, load_config
from yadof.job_template import validate_task

workspace = WorkspaceContext.from_path("path/to/workspace")
config = load_config(
    workspace,
    overrides={"EVALUATION_MODE": "local"},
)
task = validate_task(config.workspace)

print(config.describe())
print(task.parameter_names)
print(task.objective_names)
```

Omitting the path selects the current directory. `WorkspaceContext` resolves root
`config.py`, `job_template/`, jobs, recorded data, surrogate checkpoints, logs, and
tool output to absolute paths but does not create them. Relative path settings are
resolved from the workspace root; an explicit absolute value may select another
writable location.

Configuration precedence is:

```text
package defaults < workspace config.py < temporary API/CLI override
```

`load_config()` rejects unknown uppercase settings, invalid types/modes, and missing
task paths. Temporary overrides affect only the returned values and never rewrite
`config.py`; `config.describe()` shows every final value and its source.

A package-era workspace `job_template/` owns only mutable task inputs:
`parameters_constraints.py`, `workflow.py`, `calc_cost.py`, active `*_com.py`
adapters, simulator/custom inputs, lookup tables, and other assets. Stable
`Parameter`, rawData, cost-helper, and task-query APIs come from
`yadof.job_template`. Task files may use reasonable sibling absolute or relative
imports; each query reloads current source without permanently changing `sys.path`
or sharing local modules with another workspace.

This stage does not prepare or run a job. The forthcoming `init`, `check`, local
evaluation, and run stages will consume these APIs.

## Packaged Documentation

The repository-root `dev_doc/` and `user_doc/` directories remain authoritative.
Wheel builds include read-only snapshots as package data so document lookup works
outside the repository and with a non-writable installation. The wheel does not
contain the active task model, runtime jobs, recorded history, checkpoints, caches,
or secrets.
