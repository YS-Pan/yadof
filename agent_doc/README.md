# yadof agent guide

This is the installed entry point for an AI agent that answers questions about
yadof or prepares a yadof optimization task. Treat the installed package and these
version-matched documents as read-only sources of truth. Every task edit and runtime
artifact belongs to an explicit writable workspace.

## First decide the request type

- For a question, list the available documents and read only the relevant pages.
- For task creation or modification, follow the complete task-authoring reading
  order below before editing the workspace.
- For framework implementation details not specified by these documents, inspect
  the relevant installed `yadof` code. Never modify files in site-packages.

Use the installed documentation interface from any directory:

```powershell
python -m yadof docs list agent
python -m yadof docs show agent package_foundation.md
python -m yadof docs bundle agent
```

## Task-authoring reading order

1. Read [package_foundation.md](package_foundation.md) for installation, workspace
   layout, versioning, and safe `init`/`check` behavior.
2. Read [optimization_workflow.md](optimization_workflow.md) to define parameters,
   a workflow, rawData, and costs.
3. Read [config_and_run.md](config_and_run.md) for configuration precedence,
   local/distributed smoke, start/resume, history, and viewing commands.

Task author references:

- [workflow_typical_patterns.md](workflow_typical_patterns.md)
- [calc_cost_typical_patterns.md](calc_cost_typical_patterns.md)
- [adapters/README.md](adapters/README.md) and the adapter-specific pages

When a source checkout is available, its top-level `examples/` directory may provide
additional task-specific reference workspaces. Those examples are not installed
package resources and must not be assumed to exist in a pip-only environment.

## Operating rules

- Run `yadof init PATH` rather than inventing the workspace marker or starter files.
- Edit only the selected workspace, normally `config.py`, `job_template/`, and
  task-owned assets. Do not edit installed package resources.
- Run `yadof check --workspace PATH` after generating or modifying task files.
- Do not run an edited task's smoke test or optimization unless the user explicitly
  authorizes execution of the real workflow; it may launch expensive software.
- Report created files, validation results, unresolved task assumptions, and the
  exact command the user can approve to start the next execution stage.

The supported command surface is `yadof --help`, `version`, `docs`, `init`, `check`,
`smoke-test`, `run`, `view`, `history`, and `task`. Commands that can execute real
software or delete history make that behavior explicit. Framework self-tests are
`pytest` tests and are different from a task smoke test.
