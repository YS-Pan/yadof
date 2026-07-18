# Installed Package, Workspace, And Local Evaluation

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

The installed package exposes repository-independent information, workspace
preparation/diagnosis, and explicit local workflow evaluation:

```powershell
yadof --help
yadof --version
yadof version
yadof docs user
yadof docs dev
yadof init [PATH]
yadof check --workspace PATH
yadof smoke-test --workspace PATH --mode local [--real-task]
```

The document commands print UTF-8 entry content. They do not open a GUI and do not
write into the installed package.

`yadof init` defaults to the current directory. It creates only:

```text
config.py
job_template/
  parameters_constraints.py
  workflow.py
  calc_cost.py
.yadof/
  workspace.json
```

The starter is a minimal pure-Python/NumPy task with generic `input_value` and
`objective` placeholders. It selects no simulator, vendor, adapter, model, or
physical result. Initialization validates a temporary copy before publishing it.
Existing target files stop initialization and are listed exactly; unrelated files
are preserved. Repeating `init` on a complete matching workspace confirms it without
rewriting config, task files, or history. It is not an upgrade or repair command.

`yadof check` reports the workspace directory and marker, effective config, task
parameter/objective imports, `workflow.py` syntax, any task-local flat `rawData`
directory that already exists, and read-only prerequisites for the selected local
or distributed backend. It never imports or executes `workflow.py`, creates runtime
directories, runs a simulator, installs dependencies, or changes HTCondor. A missing
distributed executable is an administrator action reported as an error.

`yadof smoke-test` is intentionally different: it executes `workflow.py` for exactly
one deterministic midpoint individual, with no generation index and no timeout. An
unchanged generic starter can run directly. If any task file was edited or any
adapter/asset was added, the command refuses before creating a job unless you add
`--real-task`. That flag is explicit intent to run a task that may launch a simulator,
custom program, or otherwise expensive workflow. Package self-tests such as
`pytest -q` do not run this real-task path.

## Current Transition Boundary

Workspace job preparation/local evaluation and workspace-local history now live
under `yadof.evaluate_manager` and `yadof.recorded_data`. Optimization, surrogate,
user tools, and distributed evaluation still live under `project/`. Continue using
the source-tree full-campaign workflow in `optimization_workflow.md` and
`config_and_run.md` until their ordered package stages replace those entry points.

The package does not provide a `project.*` compatibility alias and does not yet
implement `run`, history, view, task-editing, or distributed-smoke commands. Their
absence is intentional rather than an installation error. `init` and `check` never
evaluate; `smoke-test` evaluates and records once but does not start optimization.

## Available Workspace Python APIs

The installed package can already represent and validate the package-era workspace
boundary without creating runtime state:

```python
from yadof import WorkspaceContext, load_config
from yadof.evaluate_manager import evaluate_population, run_smoke_test
from yadof.job_template import validate_task
from yadof.recorded_data import (
    get_historical_results,
    get_rawdata_diagnostics,
    list_records,
)

workspace = WorkspaceContext.from_path("path/to/workspace")
config = load_config(
    workspace,
    overrides={"EVALUATION_MODE": "local"},
)
task = validate_task(config.workspace)

print(config.describe())
print(task.parameter_names)
print(task.objective_names)

# Exactly one midpoint individual, local, no timeout:
print(run_smoke_test(config.workspace))

# Normal local rows use effective timeout/worker settings:
print(evaluate_population(config.workspace, ((0.25,), (0.75,))))

# Completed, failed, and timed-out records stay inspectable. History derives
# normalized variables and costs from the current task files:
print(list_records(config.workspace))
print(get_historical_results(config.workspace))
print(get_rawdata_diagnostics(config.workspace))
```

Omitting the path selects the current directory. `WorkspaceContext` resolves root
`config.py`, `job_template/`, jobs, recorded data, surrogate checkpoints, logs, and
tool output to absolute paths but does not create them. Relative path settings are
resolved from the workspace root; an explicit absolute value may select another
writable location.

Every recorded-data API takes the workspace as its first argument. Pass the
effective `config.workspace` when `config.py` overrides `RECORDED_DATA_DIR` or the
task path. Successful, failed, and timed-out evaluations append compact rows below
that context's recorded-data directory:

```text
recorded_data/
  indMeta.jsonl
  indMeta.jsonl.lock
  rawData.npz
  optMeta/
    optMeta.jsonl
```

`rawData.npz` is a zip archive whose members are named `job_name/file.npz`.
`indMeta.jsonl` stores raw variables, archive member names, scrubbed rawData
metadata, status, workflow timing, and run/generation context. It does not store
costs or normalized historical variables. Those are recalculated on every query
from the current `calc_cost.py` and parameter ranges. Invalid archived rawData is
kept as evidence, skipped from default history/training views, and reported through
`get_rawdata_diagnostics()`.

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

Prepared jobs are created only below the effective `JOBS_DIR`. Each job combines:

- the assigned `parameters_constraints.py` snapshot,
- workspace `workflow.py`, every non-conflicting task-local adapter, and arbitrary
  task assets/resources,
- package-owned `worker_misc.py`,
- `yadof_worker_config.json` containing only yadof/workspace provenance and effective
  local mode, timeout, and worker count.

The package reserves `worker_misc.py` and `yadof_worker_config.json` in a task
payload; a same-named workspace file is an error and is never overwritten.
Submit-side `calc_cost.py` is not copied. A workflow writes flat rawData and lifecycle
metadata only, then the submit process validates and archives rawData below the
effective `RECORDED_DATA_DIR` before deriving the returned cost tuple through the
current workspace `calc_cost.py`. A workflow-created `cost.json` makes the job fail
and is removed. A recording or dynamic-cost failure affects only that individual;
other local rows continue and the failed row returns `inf`.

## Packaged Documentation

The repository-root `dev_doc/` and `user_doc/` directories remain authoritative.
Wheel builds include read-only snapshots as package data so document lookup works
outside the repository and with a non-writable installation. The wheel does not
contain the active task model, runtime jobs, recorded history, checkpoints, caches,
or secrets.
