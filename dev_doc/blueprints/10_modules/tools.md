# Module blueprint: tools

## Boundary

`yadof.tools` is optional, user-launched, workspace-explicit functionality. Core
optimization/evaluation never imports it. Tools read public task/recorded APIs,
present diagnostics, and write only user-requested workspace tool output or
confirmed task edits. Pool/system administration remains under `admin_tool/`.

## Views and history

Cost/time views derive current values from public history/task APIs and write
relative outputs below the configured tool directory. Cost supports selected
records/objectives. Time supports status filtering and owns elapsed time, failure
rate, execute-machine color, and typed error occurrence reporting. Machine legend
entries show the bare machine name plus that machine's average recorded elapsed
time. It prefers `execute_machine` from worker-support-written individual metadata,
then uses source-labeled `condor_execute_machine` only when timeout prevented the
worker file from returning. A never-executed job remains `unknown`; generic
scheduler ClassAds do not override worker identity. Historical timeout rows may
derive the same display-only fallback from their stored `condor_log_tail`, without
reading job directories or changing records. Each error type occupies a left-
labeled horizontal band near the plot top, with the label vertically centered on
its line; marker fill identifies the execute machine and the outer ring identifies
the error type. The failure-rate trend is highly transparent.

Individual CLI view commands write timestamped PNGs by default, accept `--output`
to override the destination, and accept `--summary-only` to suppress plotting.
`view all` invokes cost and time with their normal defaults, prints two labeled
summaries, and uses one timestamp for the two default image names. The
views do not mutate durable evidence. History clear requires explicit confirmation,
resolves and validates exact workspace-owned targets, and avoids package or
unrelated paths.

## Surrogate checkpoint viewer

`tools/surrogate_viewer/` is an optional, relatively independent GUI subtree. It
loads one explicit workspace, predicts saved checkpoint rawData/current costs,
compares selected recorded individuals, and calculates cancellable in-memory
cross-generation error aggregates. Its backend alone adapts package checkpoint,
recorded-data, and rawData internals; this includes describing every rawData
dimension, extracting user-selected 0D/1D/2D stored-grid slices, and requesting
conditional-INR values at arbitrary fixed coordinates. Stored-grid selections keep
the legacy reconstruction path; off-grid selections interpolate checkpoint scaler
arrays and do not claim recorded truth. UI modules consume immutable viewer values
and render scalars, curves, or filled color contours. The tool never trains,
launches workflows, edits checkpoints, writes audit caches, or joins the non-GUI
`view all` command.

The subpackage root is lightweight and resolves backend convenience exports lazily.
Torch, Matplotlib, and Tkinter are loaded only when the viewer is actually used.
Detailed architecture, module, file, and terminology contracts remain under the
subtree's own `dev_doc/`; yadof's main developer README links to that entry.

### Cost/time plot alignment contract

Unless a requested change explicitly says otherwise, `view_cost.py` is the visual
reference and `view_time.py` must remain aligned with it. Update both files and the
cross-view style test whenever a shared value changes. The aligned commands and
values are:

| Concern | Matplotlib command / constant | Default |
|---|---|---|
| Figure size | `plt.subplots(figsize=PLOT_FIGSIZE)` | `(5.5, 3.5)` inches |
| Raster resolution | `fig.savefig(..., dpi=PLOT_DPI)` | `600` dpi |
| Medium text | `PLOT_FONT_SIZE` | `10` pt |
| Title / tick / legend / generation text | explicit `fontsize` constants | `11 / 8 / 7 / 8` pt |
| Axis / trend / event / grid width | explicit width constants | `0.8 / 2.0 / 1.2 / 0.4` pt |
| Combined-cost average width | `COMBINED_TREND_LINE_WIDTH` in viewCost | `4.0` pt |
| Average cost/time trend opacity | `TREND_LINE_ALPHA` | `0.25` |
| Ordinary Combined-cost and viewTime marker diameter / ring width | `SCATTER_MARKER_SIZE` / `SCATTER_EDGE_LINE_WIDTH` | `3.0` pt / `0.4` pt |
| Pareto emphasis in viewCost | marker area / ring width | `60.0` pt² / `0.75` pt |
| Generation background | `axvspan(..., facecolor="black", alpha=0.1)` | odd generations only |
| Optimization-start dashes | `linestyle=(0, (4, 4))` | butt dash caps |
| Hash-change dashes | `linestyle=(4, (4, 4))` | complementary butt dash caps |
| Event-line opacity | `EVENT_LINE_ALPHA` | `0.25` |
| Legends | adjacent lower-left data/event legends | axes-edge pad `0.015`; `framealpha=0.6`; event names `Opt. start`, `Hash change` |

Plot-specific colors, axes, scientific data series, and domain labels may differ.
Shared presentation values do not drift independently: make a visual change in
`view_cost.py` first, mirror it in `view_time.py`, and update the alignment table
and tests in the same change.

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
