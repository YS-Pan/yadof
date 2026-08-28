# Module blueprint: package/workspace foundation

## Responsibility

The foundation separates immutable installed framework resources from mutable,
explicitly selected user workspaces. Distribution metadata has one version source
and one console entry point. Wheel/sdist membership is allowlisted around package
code, generic templates/adapters, and version-matched documentation. The top-level
`yadof-benchmark/` project is a separate distribution with its own installed
package resources and console entry point; it is not a yadof package resource or
implicit yadof workspace.

The current package version is 0.4.2. Recorded history uses immutable standard-ZIP
segments and immutable metadata event files below the workspace recorded-data root.

## Workspace contract

`WorkspaceContext` is an immutable absolute value containing root, config, fixed
submit, evaluate-side task,
jobs, recorded-data, checkpoint, log, tool-output, and fast scratch paths. Relative configuration
paths resolve from its root. Stateful public APIs accept a context or workspace path;
they never find user state relative to package source or a process-global project.

`init` stages and validates a generic local template, then publishes it without
overwriting existing files. The portable `.yadof/workspace.json` marker is published
last and records the template name plus package/schema provenance; it does not
authorize repair or file replacement. The template publishes `submit/calc_cost.py`, mandatory
`submit/optimization.py`, and canonical parameter/workflow sources below
`job_template/`. The generic workflow contains only its task-specific calculation
and calls package worker support, which records execute-side machine identity and
the fixed lifecycle metadata. The generic cost module demonstrates package
`soft_cost()` normalization from fixed physical thresholds into a dimensionless
`[0, 1]` minimization objective with task error cost `1.0`. `check` is read-only and reports marker, required
files, task and strategy-construction contracts, disjoint paths, and optional static rawData diagnostics.
When fast is selected, check also requires callable task-owned
`evaluation.py:evaluate_rawdata()` and a scratch path disjoint from task/jobs/history.
Additional user-created directories for task helpers, debugging evidence, and
exported artifacts may coexist below the workspace root. Init/check do not reject
or claim them, configured reserved paths retain their framework meaning, and only
content deliberately selected by preparation becomes job payload.

## Task loading and resources

Task loading compiles fresh workspace source from an explicitly selected `submit/`
or `job_template/` root in temporary namespaces and supports
same-directory helpers/packages without lasting `sys.path` or module-cache
pollution. Two workspaces may use identical helper module names safely. Package
resources are read-only and accessed through `importlib.resources`; repository
examples and benchmark automation are tracked source-checkout resources, not
packaged resources or package runtime write locations. Benchmark output resolves
only from its explicit/default runs-root contract and must remain disjoint from
frozen inputs and package source.

Workspace implementation lives under `yadof.workspace`: `context`, `manifest`,
`init`, and `check` separate the public path value from creation and diagnostics.

## Invariants

- Initialization never silently merges, repairs, or rewrites a workspace.
- Checking never launches the workflow, trains/evaluates, or mutates task/runtime state.
- Configured framework paths never overlap fixed `submit/`, `job_template/`, or one another.
- Package code remains functional when site-packages is read-only.
- The yadof wheel/sdist excludes concrete models, workspaces, jobs, records, caches,
  logs, checkpoints, credentials, examples, and benchmark orchestration/resources.
- Loaded workspace modules and helper names are removed after use.
- Unreserved user-created workspace directories remain user-owned and are not
  inferred as framework state or prepared-job input.
