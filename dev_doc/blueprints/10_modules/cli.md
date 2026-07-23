# Module blueprint: cli

## Responsibility

`yadof.cli` is the installed, repository-independent command package. Public `main`
and `build_parser` route version, documentation, workspace initialization/checking,
standalone smoke, optimization run/resume, history/view, and task utilities. Commands
return stable exit codes and present actionable workspace/job diagnostics rather than
tracebacks for expected user errors.

Heavy optimization/simulator/tool dependencies are loaded lazily behind their
commands. `version`, help, and documentation stay lightweight and read-only.

## Workspace and execution commands

Workspace-mutating commands require explicit targets. `init` never overwrites;
`check` never executes. `smoke-test` runs exactly one midpoint real task without
timeout and requires explicit intent for an edited non-default task. `run` validates
task/config, applies CLI overrides without rewriting config, handles optional smoke,
supports start/resume/generation counts, displays progress, and can stop on an
all-infinite generation with recent job diagnostics.

Documentation uses an explicit `list`, `show`, and `bundle` action model. Paths are
audience-relative and traversal is rejected. CLI code contains no duplicate
documentation body and never requires callers to locate site-packages.

Task utilities use software namespaces before actions that are not framework-
generic. HFSS parameter extraction is `yadof task hfss extract-parameters`; another
software may add its own `yadof task <software> extract-parameters` without claiming
or overloading a generic task action. Do not retain ambiguous compatibility aliases
when a command is moved into its current namespace.

## Invariants

- CLI routing does not duplicate core implementation or documentation text.
- Read-only commands do not create workspace/runtime files.
- Real external execution is clearly distinguishable from package self-tests.
- All stateful commands pass an explicit workspace into public APIs.
