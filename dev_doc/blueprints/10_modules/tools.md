# Module blueprint: tools

## Boundary

`yadof.tools` is optional, user-launched, workspace-explicit functionality. Core
optimization/evaluation never imports it. History tools read public task/recorded
APIs, present diagnostics, and write only user-requested workspace tool output or
confirmed task edits. Pool installation and configuration remain under
`admin_tool/`; the explicitly launched Condor GUI may send a user-authorized
machine drain or job removal request through the installed Condor client.

## Views and history

The Windows `condor_gui.py` desktop controller lives in `tools`. Its thin
double-clickable `condor_gui.pyw` source-checkout launcher lives at the repository
root. The portable installed launcher lives under `src/yadof/tools/` and is
published both in the package and beside `yadof-gui.exe` in `Scripts/` by ordinary
wheel installation. On Windows it calls that environment's generated executable,
preserving arguments and exit status even when `.pyw` file associations select
another Python. The package copy derives the same Scripts location from its
site-packages layout. A missing executable never falls back to another environment.
The source-checkout `.pyw` prefers `.venv` in the checkout, then in its parent,
and otherwise uses its current interpreter. It forwards exact arguments to the
selected environment before importing yadof. An interpreter already in the same
environment does not relaunch. These relative conventions require yadof to be
installed in that environment and contain no machine-specific path. The installed
`yadof-gui` entry point retains its own installation environment.
These entry points are explicitly operational, not passive history viewers.
The installed `yadof-gui`
GUI script opens one explicit workspace, starts
the existing `yadof run` CLI in a child process with visible generation bounds,
prefilling the process working directory's `workspace` folder when no path is
supplied. The checkout launcher prefers its adjacent `workspace` directory when
present, since Windows double-click launches may start in another directory. The
**选择文件夹…** button only opens a directory chooser and selects its result;
cancellation retains the selection and no files or worker commands are created.
The separate **初始化 workspace** button executes the installed
`python -m yadof init PATH` CLI for the current path on a worker using the GUI's
console interpreter. It does not choose or switch directories. Queued completion
restores controls and reports success or the CLI error. Initialized workspaces use
the CLI's idempotent validation, preserving task edits and history; conflicts are
not overwritten. Run, clear and history views require a workspace marker and
prompt for explicit initialization when it is missing, without automatic setup.
**清空 workspace** previews the selected root
and configured jobs, recorded-data, checkpoint, and optimization-state paths in a
default-No confirmation.
It calls `clear_history(confirm=True, all_recorded_data=True)` on a worker and
resets start generation to zero and progress only after successful completion.
This explicit full reset deletes even extra entries below recorded data, while
the normal history-clear API/CLI retains them. Configuration, task sources, marker,
and general tool output survive. The GUI blocks workspace edits, launching and
clearing during initialization, startup, running, stopping, views or clearing,
including the interval before the subprocess-start event arrives. Views are
serialized and cannot overlap initialization or clearing; queued worker results
release controls on the Tk thread. Cleanup errors warn about possible partial
deletion and leave the generation unchanged.
The controller maps a default-checked **启用 smoke job** checkbox to an explicit
`--smoke-test` or `--no-smoke-test` override for each launch without modifying
workspace configuration. It parses the child's generation-scoped population
progress lines on the Tk event thread to update a determinate bar. HTCondor's
`pending=N/T` line drives the bar as `(T-N)/T` and labels the remaining count;
generation outcome lines provide the fast/local fallback. Smoke batches use their
own pending count, then the next generation resets the bar.
It
stops that child process tree before running the user-requested global
`condor_rm -all`, and supports selected-mode drain and cancellation for a machine.
Condor
status polling uses tab-delimited ClassAd attributes, displays both Name and
Machine, and converts Disk KiB to a displayed MB value. Drain mode selection offers
graceful, quick, and fast; drain and cancel-drain commands both target the selected
slot's `Machine` attribute, with cancellation sent as `condor_drain -cancel`. If
HTCondor cannot locate the StartD by that Machine value, retry the same command
with the selected ClassAd's full `MyAddress`.
Tk events stay on the main thread; queries, tool views, and commands run on workers
and report through a queue. Cost/time buttons call their existing tool APIs. The
error button displays failure rows from `view_time` rather than adding a parallel
history interpreter. Its sortable table retains typed event times and worker-
machine identities; each row resolves its job name beneath the configured
workspace jobs root so a double-click opens that exact folder. Missing or escaping
folders cannot be opened.

Cost/time views derive current values from public history/task APIs and write
relative outputs below the configured tool directory. Cost supports selected
records/objectives. It treats malformed, non-numeric, non-finite, empty, average-
overflow, and minority-width cost-history rows as isolated display failures,
reports bounded issue details in the summary, and plots the remaining rows at their
original evaluation indices. Optional metadata annotation failures do not block
cost data, and unavailable task objective names use generic labels. It fails only
when core history cannot be read or no plottable row remains. Corrupt candidates
and segments are reported as bounded ignored-record diagnostics while readable
siblings remain usable. Time supports status filtering and owns elapsed time, failure
rate, execute-machine color, and typed error occurrence reporting. Machine legend
entries show the bare machine name plus that machine's average recorded elapsed
time across completed evaluations; failed evaluations remain visible but do not
enter machine time averages. Timing rows prefer workflow or execute starts from the
individual record or nested job metadata and use batch publication time only as a
last resort. It prefers `execute_machine` from worker-support-written individual
metadata,
then uses source-labeled `condor_execute_machine` only when timeout prevented the
worker file from returning. A never-executed job remains `unknown`; generic
scheduler ClassAds do not override worker identity. Historical timeout rows may
derive the same display-only fallback from their stored `condor_log_tail`, without
reading job directories or changing records. Each error type occupies a left-
labeled horizontal band near the plot top, with the label vertically centered on
its line; marker fill identifies the execute machine and the outer ring identifies
the error type. The failure-rate trend is highly transparent.

The time view scales completed elapsed data into minutes, seconds, or milliseconds
automatically: minute-scale data stays in minutes, sub-minute data uses seconds,
and sub-second data uses milliseconds. Its finite completed-data limit is based on
the observed maximum and reserves the existing upper error-band region instead of
imposing a one-minute minimum.

Individual CLI view commands write timestamped PNGs by default, accept `--output`
to override the destination, and accept `--summary-only` to suppress plotting.
Cost CLI calculation renders streamed candidate reinterpretation progress on stderr:
the exact candidate total is deliberately unknown until the one-pass read completes,
then the final frame reports the precise candidate count. While streaming, its bar
fill uses the frozen segment position, so the visual indicator advances without
requiring an extra ZIP scan. The final summary remains on stdout. One cost command
freezes its task parameters/cost callback and finalized segment names, then combines
rawData decode, schema validation, normalization, and cost recalculation while each
segment ZIP is open once. The cost PNG places the arithmetic
`avg. cost` on the left objective axis. Its right axis
shows a shaded hypervolume band whose upper boundary accumulates all generations
and whose lower boundary uses only the current generation, both against the fixed
normalized reference `(1, ..., 1)`. Each cumulative calculation retains only its
nondominated front before invoking the HV indicator. Plot styling and label
placement may evolve as long as the two series remain distinguishable and the
scientific values are unchanged. Cost
history implementation lives in the reusable `tools/cost_viewer/`
subpackage; `tools/view_cost.py` is only the compatibility import facade.
`view all` invokes cost and time with their normal defaults, prints two labeled
summaries, and uses one timestamp for the two default image names. The
views do not mutate durable evidence. History clear requires explicit confirmation,
resolves and validates exact generated targets, holds the campaign OS lock throughout
mutation, refuses an active campaign, and protects task sources, configuration,
workspace marker and the lock itself. Full recorded-data clearing additionally
requires every deletion target to remain inside the selected workspace.

## Surrogate checkpoint viewer

`tools/surrogate_viewer/` is an optional, relatively independent inspection
subtree. It loads one explicit workspace, predicts saved checkpoint
rawData/current costs, compares selected recorded individuals, and calculates
cancellable in-memory cross-generation error aggregates. Its backend alone adapts
package checkpoint, recorded-data, and rawData internals; this includes describing
every rawData dimension, extracting user-selected 0D/1D/2D stored-grid slices, and
dispatching fixed-coordinate queries to the selected conditional-INR or experimental
hierarchical-CAE checkpoint adapter. Stored-grid selections keep each method's
checkpoint-grid reconstruction path; conditional-INR off-grid selections interpolate
checkpoint scaler arrays, while coordinate-enabled hierarchical CAE uses its declared
all-axis in-domain readout. Neither path claims recorded truth. UI modules consume
immutable viewer values and render scalars, curves, or two-dimensional color plots.
`report.py` turns backend metadata and selected audit matrices into stable terminal
text or schema-versioned JSON, using `null` for missing finite aggregates and
stderr for optional progress. `inspection.py` resolves one exact real case and
builds a finite/null-safe payload with at most 4096 inline selected-plot scalars;
`renderer.py` is a pure Figure/Agg 0D/1D/2D boundary and `errors.py` owns stable
terminal runtime error payloads. Inspection writes nothing by default. Explicit
output alone publishes full selected NPZ arrays, optional one-dimensional CSV, an
Agg PNG, then a relative-path/size/SHA-256 manifest inside a new or empty directory
without replacement. The tool never trains, launches workflows, edits checkpoints,
writes audit caches, or joins the non-GUI `view all` command.

The subpackage root is lightweight and resolves backend convenience exports lazily.
Torch, Matplotlib, and Tkinter are loaded only when the viewer is actually used.
Detailed architecture, module, file, and terminology contracts remain under the
subtree's own `dev_doc/`; yadof's main developer README links to that entry.

### Cost/time presentation relationship

Cost and time plots should look like related yadof tools and remain legible when
shown together, but identical Matplotlib constants are not a compatibility
contract. Share style values when both views genuinely benefit from the same
choice; allow either view to evolve independently when its data needs differ.
Tests verify the scientific series, labels needed to interpret them, and successful
rendering. They do not freeze figure size, DPI, font sizes, line widths, opacities,
dash phases, generation-label coordinates, legend anchors, or exact artist call
structure.

## Task utilities

Task tools list/copy packaged adapters without overwriting user edits and extract
HFSS parameters with backup and confirmation.
The CLI exposes software-specific extraction below `yadof task hfss`, not as a
generic task action that future software tools would have to overload.
HFSS extraction directly recognizes both standalone Optimetrics variable records
and optimization attributes embedded in `VariableProp(...)`; it uses `Min`/`Max`
for continuous variables and discrete `Level` values before attempting a PyAEDT
fallback.

## Invariants

- Every command takes an explicit workspace and respects effective output paths.
- No concrete project/design/objective assumptions enter generic framework tools.
- Potentially destructive history/task edits are previewed/confirmed and recoverable
  through backup where applicable.
- New simulator-specific actions get their own software namespace.
- The viewer is read-only, explicitly launched, and outside core runtime imports.
