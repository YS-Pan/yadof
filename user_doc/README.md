# user_doc README

`user_doc/` stores documentation for people who use yadof to define and run an
optimization task. It is also the entry point for an AI assistant when the user asks
for help preparing a simulation file, task template, workflow, cost calculation, or
run configuration.

These documents describe user-facing task work. They are intentionally different
from `dev_doc/`, which describes framework design and maintainer contracts.

## Reading Guide

When collecting user-side context, read these files in full:

- `optimization_workflow.md`
- `config_and_run.md`

Then read the files that match the current work:

- Read `workflow_typical_patterns.md` when creating or editing `project/job_template/workflow.py`.
- Read `calc_cost_typical_patterns.md` when creating or editing `project/job_template/calc_cost.py`.
- Read `com_lib/README.md`, then the matching `com_lib/*.md` adapter document, when choosing, copying, or calling a `_com.py` file.

Do not read `dev_doc/` as part of a normal `user_doc` pass. `user_doc/` is allowed to
stand on its own for user task setup. If the user separately asks for framework
development, architecture changes, or maintainer reasoning, start from
`dev_doc/README.md` instead.

## Core User Rules

The normal task path is:

```text
parameters_constraints.py
  + workflow.py
  + active *_com.py files
  + simulator/custom input files
  -> rawData/*.npz
  -> calc_cost.py
  -> optimization costs
```

Keep these boundaries:

- `workflow.py` generates rawData only. It must not write `cost.json` or final costs.
- `calc_cost.py` converts rawData into objective costs.
- Files in `project/com_lib/` are adapter sources or references. A workflow uses an adapter only after the needed `_com.py` file is copied into `project/job_template/`.
- `project/config/key.py` is the short generic key config, `project/config/all.py` contains full generic run settings, and `project/config/specific/` contains settings tied to one simulator or vendor.
- Historical rawData may be reused when `calc_cost.py` or parameter ranges change, but the user must delete or ignore old history if old rawData no longer represents the new task.

## Document Roles

### `optimization_workflow.md`

Step-by-step user workflow for preparing a new optimization task: simulator files,
`parameters_constraints.py`, adapter files, `workflow.py`, `calc_cost.py`, config,
smoke test, and optimization launch.

### `workflow_typical_patterns.md`

Typical structure of `workflow.py`: how it reads variables, writes lifecycle metadata,
generates schema-valid rawData, calls HFSS or pure-Python adapters, and handles errors.

### `calc_cost_typical_patterns.md`

Typical structure of `calc_cost.py`: how it loads rawData, extracts values for
objectives, defines costs, handles constraints, returns error costs, and optionally
provides rawData importance weights for surrogate training.

### `com_lib/`

Per-adapter usage notes for `_com.py` files in `workflow.py`. Start with
`com_lib/README.md`, then read the document for the specific adapter, such as
`com_lib/hfss_com.md` or `com_lib/test_com.md`.

### `config_and_run.md`

User-facing configuration and launch notes for `project/config/key.py`, `project/config/all.py`, matching modules under `project/config/specific/`, smoke tests,
and `start_optimization_aedtopt.cmd`.

## Maintenance Rules

Update `user_doc/` when a user-facing task setup step changes, especially when:

- The expected shape of `workflow.py`, `calc_cost.py`, rawData `.npz` files, or adapter calls changes.
- A new `_com.py` adapter is added for users to copy into `job_template`; add a matching `user_doc/com_lib/<adapter>.md`.
- `project/config/key.py`, `project/config/all.py`, or a module under `project/config/specific/` gains or renames a setting users must edit before running.
- The recommended smoke-test or optimization launch command changes.

Avoid duplicating framework architecture details from `dev_doc/`. If the same concept
needs both views, keep `user_doc/` focused on what the user does and keep `dev_doc/`
focused on why the framework is designed that way.
