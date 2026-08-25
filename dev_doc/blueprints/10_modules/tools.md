# Module blueprint: tools

## Boundary

`yadof.tools` is optional, user-launched, workspace-explicit functionality. Core
optimization/evaluation never imports it. Tools read public task/recorded APIs,
present diagnostics, and write only user-requested workspace tool output or
confirmed task edits. Pool/system administration remains under `admin_tool/`.

## Views and history

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
resolves and validates exact workspace-owned segment and event targets, refuses
while the campaign OS lock is held, and avoids package or unrelated paths.

## Surrogate checkpoint viewer

`tools/surrogate_viewer/` is an optional, relatively independent inspection
subtree. It loads one explicit workspace, predicts saved checkpoint
rawData/current costs, compares selected recorded individuals, and calculates
cancellable in-memory cross-generation error aggregates. Its backend alone adapts
package checkpoint, recorded-data, and rawData internals; this includes describing
every rawData dimension, extracting user-selected 0D/1D/2D stored-grid slices, and
requesting conditional-INR values at arbitrary fixed coordinates. Stored-grid
selections keep the checkpoint-grid reconstruction path; off-grid selections interpolate
checkpoint scaler arrays and do not claim recorded truth. UI modules consume
immutable viewer values and render scalars, curves, or two-dimensional color plots.
`report.py` turns backend metadata and selected audit matrices into stable terminal
text or schema-versioned JSON, using `null` for missing finite aggregates and
stderr for optional progress. The tool never trains, launches workflows, edits
checkpoints, writes audit caches, or joins the non-GUI `view all` command.

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
