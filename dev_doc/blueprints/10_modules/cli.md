# Module blueprint: cli

## Responsibility

`yadof.cli` is the installed, repository-independent command package. Public `main`
and `build_parser` route version, documentation, workspace initialization/checking,
standalone smoke, optimization run/resume, history/view, the optional surrogate
viewer, and task utilities. Commands return stable exit codes and present
actionable workspace/job diagnostics rather than tracebacks for expected user
errors.

Heavy optimization/simulator/tool dependencies are loaded lazily behind their
commands. `version`, help, and documentation stay lightweight and read-only.

## Workspace and execution commands

Workspace-mutating commands require explicit targets. `init` never overwrites;
`check` never executes. `smoke-test` runs exactly one midpoint real task without
timeout and requires explicit intent for an edited non-default task. `run` validates
task/config, applies CLI overrides without rewriting config, handles optional smoke,
supports start/resume/generation counts, displays progress, and can stop on an
all-infinite generation with recent job diagnostics.

Before standalone smoke blocks on execution, it flushes the workspace, selected
backend, jobs directory, and the fact that no timeout applies. Its terminal message
reports either finite costs or an actionable failure. `run --generations` defaults
to 50 when the option is omitted; explicit values still override one invocation,
and the Python optimizer API still requires its generation count.

Documentation uses an explicit `list`, `show`, and `bundle` action model. Paths are
audience-relative and traversal is rejected. CLI code contains no duplicate
documentation body and never requires callers to locate site-packages.

Task utilities use software namespaces before actions that are not framework-
generic. HFSS parameter extraction is `yadof task hfss extract-parameters`; another
software may add its own `yadof task <software> extract-parameters` without claiming
or overloading a generic task action. Do not retain ambiguous compatibility aliases
when a command is moved into its current namespace.

Cost/time view commands print their summaries and, by default, create
`cost_YYYYMMDD_HHMMSS.png` or `time_YYYYMMDD_HHMMSS.png` below the selected
workspace's configured tool-output directory. `--output` selects another path and
`--summary-only` explicitly disables image generation. `view all` invokes both
tools with one workspace and one timestamp, prints labeled results for every
successful tool, continues attempting the later tool if the first fails, and
returns failure if either tool failed. The corresponding Python tool APIs retain
`output_path=None` as summary-only behavior.

`view surrogate` is a separate GUI kind. It optionally receives one workspace,
loads `yadof.tools.surrogate_viewer.app` only inside its handler, reports missing
`viewer` dependencies without a traceback, and never participates in `view all`.
Parser construction and `view surrogate --help` must succeed in a core-only
installation.

## Invariants

- CLI routing does not duplicate core implementation or documentation text.
- Commands described as summary-only do not create workspace/runtime files; normal
  view commands may create only their documented tool-output PNG.
- Real external execution is clearly distinguishable from package self-tests.
- All stateful commands pass an explicit workspace into public APIs.
- No command other than `view surrogate` implicitly opens a desktop GUI.
