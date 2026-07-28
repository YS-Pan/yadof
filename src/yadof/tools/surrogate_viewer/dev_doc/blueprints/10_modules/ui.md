# Module blueprint: UI

## Intent

Own user interaction and visualization as two distinct workflows while keeping
model/record mechanics in the backend and asynchronous execution in the
application coordinator.

## Functionalities

Interactive tab:

- select a checkpoint, real generation, real individual, and rawData curve;
- build one normalized slider per task parameter;
- display denormalized values and legal ranges;
- debounce automatic predictions and support manual prediction;
- apply real-result vectors and clear comparison state;
- render prediction/true curves, the ensemble-member pointwise min/max band, and
  objective bars.

Heatmap tab:

- select relative/absolute error independently from quantity;
- map quantity labels to cost/rawData kind plus optional item index;
- validate per-generation sample percentage;
- display audit progress and expose cooperative Stop;
- retain the last complete audit across recalculation/cancellation;
- derive and render the selected matrix instantly.

Shared UI:

- consistent ttk styling and conventional selected-tab emphasis;
- Up/Down navigation for readonly comboboxes;
- Left/Right normalized slider movement, with larger Shift steps;
- scrollable parameter controls;
- Matplotlib navigation toolbars.

## I/O Format

The tabs accept a `SurrogateWorkspace` when loaded. The interactive tab exposes
`(checkpoint generation, normalized tuple, optional real job name)` and consumes a
`PredictionResult`. The heatmap tab emits a validated percentage and consumes
progress values or one `CrossGenerationErrorAudit`.

Plot components consume immutable result/matrix values and own their figure axes
and canvases.

## Non-Obvious Techniques

- Quantity meaning follows combobox index into `QuantityOption` values, not string
  parsing; duplicate or prefixed task names cannot change semantics.
- The heatmap uses explicit half-step cell edges so outer blocks are complete and
  generation ticks align with block centers.
- `pcolormesh(..., shading="flat")` plus `aspect="auto"` gives discrete rectangular
  cells that fill the available region.
- The displayed audit is replaced only in `finish()`, never in begin/progress/stop
  paths.
- Tk combobox popdown widgets may be Tcl path strings rather than Python widgets;
  mousewheel ancestry logic must tolerate that.

## Mutability Profile

Copy, color, spacing, label width, and annotation thresholds may change. Keyboard
access, separation of the two tabs, last-complete audit behavior, matrix semantics,
non-interpolated cells, and main-thread drawing should remain stable.
