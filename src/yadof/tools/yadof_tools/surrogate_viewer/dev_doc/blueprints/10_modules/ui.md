# Module blueprint: UI

## Intent

Own user interaction and visualization as two distinct workflows while keeping
model/record mechanics in the backend and asynchronous execution in the
application coordinator.

## Functionalities

Interactive tab:

- select a checkpoint, real generation, real individual, and rawData output;
- randomly select one available real generation and one of its individuals when a
  workspace is loaded;
- list every rawData dimension, allow at most two to be checked as plot axes, and
  give every unchecked dimension both a checkpoint-grid dropdown and an arbitrary
  finite-value entry;
- build one normalized slider per task parameter;
- display denormalized values and legal ranges;
- expose `Auto refresh`, debounce automatic predictions when enabled, and support
  manual prediction;
- apply real-result vectors and clear comparison state;
- render scalar values, prediction/true curves, the ensemble-member pointwise
  min/max display, two-dimensional color plots, and objective bars.
  Two-dimensional truth and prediction use the same color
scale in adjacent axes.
- omit recorded rawData overlays and show an explanatory note for off-grid
  coordinates while retaining objective bars calculated from the checkpoint grid.

Heatmap tab:

- select relative/absolute error independently from quantity;
- map quantity labels to cost/rawData kind plus optional item index;
- validate per-generation sample percentage;
- display audit progress and expose cooperative Stop;
- retain the last complete audit across recalculation/cancellation;
- derive and render the selected matrix instantly.

Shared UI:

- consistent ttk styling and conventional selected-tab emphasis;
- clear selected/unselected state for plot dimensions and `Auto refresh`;
- Up/Down navigation for readonly comboboxes;
- Left/Right normalized slider movement, with larger Shift steps;
- scrollable parameter controls;
- Matplotlib navigation toolbars.

## I/O Format

The tabs accept a `SurrogateWorkspace` when loaded. The interactive tab exposes
`(checkpoint generation, normalized tuple, optional real job name, PlotRequest)`
and consumes a `PredictionResult`. The heatmap tab emits a validated percentage
and consumes progress values or one `CrossGenerationErrorAudit`.

Plot components consume immutable result/matrix values and own their figure axes
and canvases. Interactive plot intent includes zero to two ordered dimension
indices plus fixed coordinates for the remaining dimensions.

## Non-Obvious Techniques

- Quantity meaning follows combobox index into `QuantityOption` values, not string
  parsing; duplicate or prefixed task names cannot change semantics.
- The heatmap uses explicit half-step cell edges so outer blocks are complete and
  generation ticks align with block centers.
- The heatmap represents each generation pair as one discrete cell and aligns
  generation ticks with cell centers; the exact Matplotlib mesh styling may vary.
- The displayed audit is replaced only in `finish()`, never in begin/progress/stop
  paths.
- Selecting dimensions or fixed coordinates issues a superseding prediction
  request so an existing off-grid plot cannot be reused for a different query; a
  third selected dimension is rejected immediately.
- Shared checkmark toggles retain native BooleanVar state, focus, and Space-key
  operation while rendering deterministic selected/unselected symbols.
- Tk combobox popdown widgets may be Tcl path strings rather than Python widgets;
  mousewheel ancestry logic must tolerate that.

## Mutability Profile

Copy, color, spacing, label width, annotation thresholds, two-dimensional artist
type, contour overlays, and mesh edge styling may change. Keyboard access,
separation of the two tabs, last-complete audit behavior, matrix semantics,
non-interpolated cells, and main-thread drawing should remain stable.
