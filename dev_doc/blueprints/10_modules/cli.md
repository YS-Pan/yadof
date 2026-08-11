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
`check` never executes and requires an explicit valid `evaluation.py` contract when
fast is selected. `smoke-test` runs exactly one midpoint real task without
timeout and requires explicit intent for an edited non-default task. `run` validates
task/config, applies CLI overrides without rewriting config, handles optional smoke,
supports start/resume/generation counts, displays progress, and can stop on an
all-infinite generation with recent job diagnostics.

`run` enables progress by default for fast, local, and distributed execution. The
generation bar advances per terminal individual and displays finished/total,
successful, error, and remaining counts while backend details continue to explain
planning, scheduling, retries, and timeouts. `--no-progress` is the explicit quiet
override; `--progress` explicitly selects the default behavior. The temporary
progress environment is restored after every invocation.

Both execution commands accept `fast`, `local`, or `distributed`. Fast feedback
states that no durable job directory exists, identifies the ephemeral scratch root,
uses exactly one worker for smoke, and reports failures from recorded history.

Before standalone smoke blocks on execution, it flushes the workspace, selected
backend, jobs directory, and the fact that no timeout applies. Its terminal message
reports either finite costs or an actionable failure. `run --generations` defaults
to 50 when the option is omitted; explicit values still override one invocation,
and the Python optimizer API still requires its generation count.

Documentation uses an explicit `list`, `show`, and `bundle` action model. Paths are
audience-relative and traversal is rejected. The current audiences are `user` for
the user-workflow guidance primarily executed by the user's AI agent, and `dev` for
maintainers. CLI code contains no duplicate documentation body and never requires
callers to locate site-packages.

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
`output_path=None` as summary-only behavior. Cost-history normalization, rawData
loading, and dynamic cost calculation automatically render a dependency-free,
bounded progress bar on stderr; interactive frames overwrite in place and leave
one final line per stage, while summaries and saved-path messages remain on stdout.
The handler imports the stable `yadof.tools.cost_viewer` package surface rather
than the legacy flat compatibility module.

`view surrogate` is a separate optional kind. Its bare/default `gui` mode
optionally receives one workspace and loads `yadof.tools.surrogate_viewer.app`
only inside its handler. Its `summary` mode prints checkpoint/history/task/rawData
metadata without model inference, while `audit` prints selected cross-generation
error matrices after one backend inference pass. Both terminal modes support text
and schema-versioned JSON, default to the current directory, never open Tkinter,
and keep optional progress on stderr. All modes report missing `viewer`
dependencies without a traceback and never participate in `view all`. Parser
construction and every `view surrogate ... --help` path must succeed in a
core-only installation.

## Invariants

- CLI routing does not duplicate core implementation or documentation text.
- Commands described as summary-only do not create workspace/runtime files; normal
  view commands may create only their documented tool-output PNG.
- Real external execution is clearly distinguishable from package self-tests.
- All stateful commands pass an explicit workspace into public APIs.
- No command other than the default/explicit `view surrogate` GUI mode opens a
  desktop GUI.
