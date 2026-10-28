# Module blueprint: package/workspace foundation

## Responsibility

The foundation separates immutable installed framework resources from mutable,
explicitly selected user workspaces. Distribution metadata has one version source
and one console entry point. Wheel/sdist membership is allowlisted around package
code, generic templates/adapters, and version-matched documentation. The top-level
`yadof-benchmark/` project is a separate distribution with its own installed
package resources and console entry point; it is not a yadof package resource or
implicit yadof workspace.
The repository-root `condor_gui.pyw` is only a source-checkout launcher. The
portable installed launcher is maintained under `src/yadof/tools/condor_gui.pyw`.
Hatch's wheel `shared-scripts` mapping also places it in `.data/scripts/`, so
ordinary pip installation publishes `Scripts/condor_gui.pyw` automatically.
Both copies remain pip-managed artifacts, replaced and removed with the package.
On Windows the script forwards exact arguments and the exit code through its
own installation's generated `yadof-gui.exe`, without importing yadof through
the potentially unrelated interpreter selected by `.pyw` file associations.
The package copy derives the Scripts location from its standard global/venv or
user-site layout. Missing entries fail rather than choosing another environment.
Non-Windows invocation uses the installed Python GUI entry directly. No fixed
drive, source checkout, extra installation script or workspace mutation is needed.

The current package version is 0.7.0. Recorded history uses immutable standard-ZIP
segments and immutable metadata event files below the workspace recorded-data root.

## Windows MSI deployment

The source-checkout administrator builder under `admin_tool/windows_installer/`
wraps an exact built wheel in a Windows x64 MSI. It stages a complete relocatable
CPython 3.11.15 prefix named `yadof_env` by copying allowlisted native runtime
manifests and only the installed distributions in the declared framework dependency
closure. The A2094 audit fixes main dependency versions; framework extras absent
there use explicitly pinned submit-host versions. Every installed file has an MSI
component and digest. No installer-time pip, network download or nested MSI occurs.
MSI File rows retain PE versions/languages, and private-prefix replacements force
all registered files to be installed. Otherwise Windows Installer can skip a
same-version executable before removing the old product, leaving an incomplete
runtime after an apparently successful upgrade. Acceptance must launch the CLI
and load native/framework dependencies again after same-version upgrade.

The full MSI UI displays a property-bound, non-editable destination and a Browse
button. A small native C DLL embedded in the Binary table is an immediate UI
custom action. It initializes COM on MSI's impersonated UI-action thread and
invokes IFileOpenDialog in folder mode, using Windows' modern Common Item Dialog
like the GUI workspace chooser. A new worker thread would lose user impersonation;
using the blocked client HWND as owner can deadlock the remote action host, so
the picker runs modally without a client owner HWND.
Selection updates INSTALLDIR through MsiSetTargetPath; cancelling returns success
without changing the previous directory. No Python or script engine is needed
before installation. Zig 0.14.1 is a build-time-only compiler; native source and
binary hashes join the manifest and product identity. A modeless progress
dialog precedes ExecuteAction and subscribes to SetProgress/Progress, ActionText
and ActionData events. Its progress comes from installer ticks,
including servicing operations, rather than a timer or simulated percentage.
Interactive acceptance must exercise selection/cancel and observe advancing
progress while an isolated test product installs, without replacing an existing
user product or its registry/shortcuts.
Derive the maximum installation-directory length from the longest payload path
in UTF-16 code units. Validate before UI confirmation and before any execute-phase
copy/removal so a deeply nested target cannot fail after partially copying files.
Provide the standard ErrorDialog property, error style, ErrorText and seven result
buttons; full-UI error handling must not depend on a missing-dialog fallback.

Private `python311._pth` plus explicit site policy exclude external site packages and Python environment
injection; private startup locates DLLs/Tcl/Tk and permits task sibling imports.
Relative launchers preserve argument quoting and CLI exit status. Per-user desktop
and Start menu shortcuts open the installed GUI without relying on `.pyw`
associations. Repair, same-version payload replacement, downgrade rejection and
uninstall use Windows Installer ownership; unknown files and external workspaces
are retained. The MSI excludes pool binaries, solver packages, development tools,
benchmarks, credentials and concrete tasks. It changes neither worker identity nor
the direct-workflow distributed contract. Build/acceptance procedures and exact
versions belong in the administrator guide, not in core runtime APIs.

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
files, task and optimization-source contracts, disjoint paths, and optional static rawData diagnostics.
It parses the exact literal program declaration without importing or executing the
source.
When fast is selected, check also requires the task-owned, versioned
`evaluation.py` session factory and a scratch path disjoint from
task/jobs/history. The template shares its session kernel with the prepared workflow.
Additional user-created directories for task helpers, debugging evidence, and
exported artifacts may coexist below the workspace root. Init/check do not reject
or claim them, configured reserved paths retain their framework meaning, and only
content deliberately selected by preparation becomes job payload.

## Task loading and resources

Task loading compiles fresh workspace source from an explicitly selected `submit/`
or `job_template/` root in temporary namespaces and supports
same-directory helpers/packages without lasting `sys.path` or module-cache
pollution. Optimization-program loading is narrower: one run freezes and
isolated-loads only `optimization.py` plus its exact statically declared helpers;
other submit sources remain generation-loaded task inputs. Two workspaces may use identical helper module names safely. Package
resources are read-only and accessed through `importlib.resources`; repository
examples and benchmark resources are tracked source-checkout concerns, not yadof
package runtime write locations. The independent benchmark package writes one
execution directly into its explicitly selected benchmark workspace, never into
yadof package source or site-packages.

Workspace implementation lives under `yadof.workspace`: `context`, `manifest`,
`init`, and `check` separate the public path value from creation and diagnostics.

## Invariants

- Initialization never silently merges, repairs, or rewrites a workspace.
- Checking never launches the workflow, trains/evaluates, or mutates task/runtime state.
- Checking never imports or calls an optimization program, and executable program
  top-level statements fail static validation.
- Configured framework paths never overlap fixed `submit/`, `job_template/`, or one another.
- Package code remains functional when site-packages is read-only.
- The yadof wheel/sdist excludes concrete models, workspaces, jobs, records, caches,
  logs, checkpoints, credentials, examples, and benchmark orchestration/resources.
- Loaded workspace modules and helper names are removed after use.
- Unreserved user-created workspace directories remain user-owned and are not
  inferred as framework state or prepared-job input.
