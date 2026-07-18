# yadof user guide

Use yadof through an installed package and an explicit writable workspace. The
package is shared framework code; every task edit and runtime artifact belongs to a
workspace.

## Start here

1. Read [package_foundation.md](package_foundation.md) for installation, workspace
   layout, versioning, and safe `init`/`check` behavior.
2. Read [optimization_workflow.md](optimization_workflow.md) to define parameters,
   a workflow, rawData, and costs.
3. Read [config_and_run.md](config_and_run.md) for configuration precedence,
   local/distributed smoke, start/resume, history, and viewing commands.

Task author references:

- [workflow_typical_patterns.md](workflow_typical_patterns.md)
- [calc_cost_typical_patterns.md](calc_cost_typical_patterns.md)
- [com_lib/README.md](com_lib/README.md) and the adapter-specific pages

The supported command surface is `yadof --help`, `version`, `docs`, `init`, `check`,
`smoke-test`, `run`, `view`, `history`, and `task`. Commands that can execute real
software or delete history make that behavior explicit. Framework self-tests are
`pytest` tests and are different from a task smoke test.
