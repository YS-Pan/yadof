# yadof

Yadof is a task-agnostic optimization framework for expensive simulator, custom
Python, and multi-program workflows. Its durable modeling chain remains:

```text
normalized variables -> rawData -> cost
```

This repository is partway through the package/workspace conversion. The installed
foundation under `src/yadof/` includes explicit workspace, effective-config, and
isolated task-loading Python APIs plus safe workspace initialization and read-only
diagnostics. It now also owns packaged job preparation, local subprocess evaluation,
and a safe standalone local smoke command. Persistence, optimization, surrogate,
tools, and distributed runtime remain under `project/` until their ordered migration
steps are completed. The package namespace does not provide a compatibility alias
for `project.*`.

## Package And Workspace Foundation

Build or install the package with a PEP 517 frontend:

```powershell
python -m pip install .
```

The installed console entry point currently exposes repository-independent
foundation commands:

```powershell
yadof --help
yadof version
yadof docs user
yadof docs dev
yadof init [PATH]
yadof check --workspace PATH
yadof smoke-test --workspace PATH --mode local [--real-task]
```

`init` publishes a small, simulator-neutral pure-Python starter only after validating
it in a temporary location. It never overwrites an existing target or repairs a
modified initialized workspace. `check` validates the workspace marker, config,
task imports, workflow syntax, static rawData, and selected backend prerequisites;
it does not run the workflow, install software, or repair external systems.

`smoke-test` executes exactly one deterministic midpoint individual with no timeout.
The unchanged generic starter can run directly; edited or additional task payloads
require `--real-task` because workflow execution may launch expensive external
software. This is distinct from package self-tests.

Local evaluation is available through the installed package. Optimization, history,
distributed evaluation, and user tools are added by later package-conversion stages;
until then, use the current `project/` APIs and launchers for full campaigns.

The installed Python API can already resolve and validate a user-owned workspace
without writing to site-packages:

```python
from yadof import WorkspaceContext, load_config
from yadof.evaluate_manager import run_smoke_test
from yadof.job_template import validate_task

workspace = WorkspaceContext.from_path("path/to/workspace")
config = load_config(workspace)
task = validate_task(config.workspace)
print(config.describe())
print(task.parameter_names, task.objective_names)
print(run_smoke_test(config.workspace))
```

The workspace owns root `config.py`, mutable files/assets under `job_template/`,
the versioned `.yadof/workspace.json` marker, and all runtime paths. Package defaults
are overridden first by workspace config and then by temporary in-memory overrides;
task modules are freshly isolated on every query so separate workspaces cannot share
import state.

## Dependency Layers

- Base: NumPy and pymoo for the core optimization/data contracts.
- `surrogate`: PyTorch-backed surrogate training and prediction.
- `plot`: plotting support for result viewers.
- `hfss`: the optional HFSS adapter dependency.
- `dev`: build, test, and artifact-validation tools.

HTCondor executables, simulator applications, and machine configuration are
administrator-provided external environment components, not pip dependencies.

## Documentation Resources

The authoritative documentation remains in `dev_doc/` and `user_doc/`. Builds map
those source trees into wheel package data, so an installed yadof can read them with
Python resource APIs without relying on a Git checkout or writing to site-packages.
