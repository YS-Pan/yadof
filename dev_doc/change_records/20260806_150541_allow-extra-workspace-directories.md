# Allow user-created workspace directories

## Request

Document that a yadof workspace may contain additional directories for task
helpers, debugging artifacts, animation-generation code, exported media, and other
task outputs.

## Decision

The workspace root is user-owned. The documented layout names framework-reserved
or conventional locations; it is not a closed allowlist. Additional directories
are permitted when their names do not collide with reserved/configured paths.

Extra directories have no automatic framework semantics. Yadof ignores them unless
configuration or task code explicitly references them, and prepared-job creation
does not recursively collect arbitrary top-level workspace content. Execute-side
assets still belong below `job_template/` or must be copied deliberately by task
code.

## Documentation changes

- The installed user guide now explicitly authorizes task/debug/export directories
  and states the reserved-path and prepared-job boundaries.
- Current architecture, package/workspace blueprints, and terminology carry the
  same ownership and payload contract.

## Verification

Build both distribution artifacts, force-reinstall the wheel into the repository
venv, confirm installed user documentation includes the new rule, run workspace
checking with a real extra visualization directory present, and run the full test
suite.
