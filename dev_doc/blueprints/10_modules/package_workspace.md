# Module blueprint: package/workspace foundation

## Responsibility

The foundation separates immutable installed framework resources from mutable,
explicitly selected user workspaces. Distribution metadata has one version source
and one console entry point. Wheel/sdist membership is allowlisted around package
code, generic templates/adapters, and version-matched documentation.

## Workspace contract

`WorkspaceContext` is an immutable absolute value containing root, config, task,
jobs, recorded-data, checkpoint, log, and tool-output paths. Relative configuration
paths resolve from its root. Stateful public APIs accept a context or workspace path;
they never find user state relative to package source or a process-global project.

`init` stages and validates a generic template, then publishes it without
overwriting existing files. The portable `.yadof/workspace.json` marker is published
last and records template/version provenance; it does not authorize repair or
automatic upgrade. `check` is read-only and reports marker, required files, task
contract, path, and optional static rawData diagnostics.

## Task loading and resources

Task loading compiles fresh workspace source in temporary namespaces and supports
same-directory helpers/packages without lasting `sys.path` or module-cache
pollution. Two workspaces may use identical helper module names safely. Package
resources are read-only and accessed through `importlib.resources`; repository
examples are tracked references, not packaged resources or runtime write locations.

Workspace implementation lives under `yadof.workspace`: `context`, `manifest`,
`init`, and `check` separate the public path value from creation and diagnostics.

## Invariants

- Initialization never silently merges, repairs, or upgrades a workspace.
- Checking never launches the workflow or mutates task/runtime state.
- Package code remains functional when site-packages is read-only.
- Wheel/sdist exclude concrete models, workspaces, jobs, records, caches, logs,
  checkpoints, credentials, and examples.
- Loaded workspace modules and helper names are removed after use.
