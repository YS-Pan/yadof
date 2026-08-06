# Module blueprint: package/workspace foundation

## Responsibility

The foundation separates immutable installed framework resources from mutable,
explicitly selected user workspaces. Distribution metadata has one version source
and one console entry point. Wheel/sdist membership is allowlisted around package
code, generic templates/adapters, and version-matched documentation.

The current package version is 0.2.0. Project history reserves 0.1.0 for the older
pre-package implementation and uses 0.2.0 for the present installable-package line.

## Workspace contract

`WorkspaceContext` is an immutable absolute value containing root, config, task,
jobs, recorded-data, checkpoint, log, tool-output, and fast scratch paths. Relative configuration
paths resolve from its root. Stateful public APIs accept a context or workspace path;
they never find user state relative to package source or a process-global project.

`init` stages and validates a generic local template, then publishes it without
overwriting existing files. The portable `.yadof/workspace.json` marker is published
last and records template/version provenance; it does not authorize repair or
automatic upgrade. The generic workflow contains only its task-specific calculation
and calls package worker support, which records execute-side machine identity and
the fixed lifecycle metadata. The generic cost module demonstrates package
`soft_cost()` normalization from fixed physical thresholds into a dimensionless
`[0, 1]` minimization objective with task error cost `1.0`. `check` is read-only and reports marker, required
files, task contract, path, and optional static rawData diagnostics.
When fast is selected, check also requires callable task-owned
`evaluation.py:evaluate_rawdata()` and a scratch path disjoint from task/jobs/history.
Additional user-created directories for task helpers, debugging evidence, and
exported artifacts may coexist below the workspace root. Init/check do not reject
or claim them, configured reserved paths retain their framework meaning, and only
content deliberately selected by preparation becomes job payload.

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
- Unreserved user-created workspace directories remain user-owned and are not
  inferred as framework state or prepared-job input.
