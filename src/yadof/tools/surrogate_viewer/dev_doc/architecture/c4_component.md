# C4 components

## Application Components

- `SurrogateViewerApp`: root lifecycle, workspace loading, executor submission,
  serial-based stale-result suppression, UI callback draining, cancellation, and
  error reporting.
- `InteractiveTab`: selectors, rawData dimension rows, zero-to-two plot-axis
  selection, grid dropdowns, arbitrary fixed-coordinate entries, slider
  construction, keyboard behavior,
  random initial real-result selection, `Auto refresh` intent, debounced prediction
  requests, selected prediction inputs, and plot selection.
- `HeatmapTab`: cost/rawData quantity mapping, error type, sampling percentage,
  progress, stop intent, last complete audit, and instant matrix selection.
- `InteractivePlot`: scalar values, rawData curves, pointwise ensemble-member
  min/max display, filled two-dimensional color contours without contour lines,
  true-result comparison, and objective bars.
- `HeatmapPlot`: non-interpolated `pcolormesh`, complete edge bounds, automatic
  rectangular aspect, edge-free flush cells, annotations, colorbar, and one-line
  title.
- `CheckmarkToggle`: keyboard-operable shared selection control with an explicit
  checkmark and high-contrast accent fill instead of theme-dependent indicator
  glyphs.

## Reporting Components

- workspace-summary builder: checkpoint/training metadata, per-generation completed
  counts, parameter ranges, objective names, and rawData dimension spans without
  loading a model;
- audit-report builder: one backend audit plus exact named cost/rawData quantity
  selection and relative, absolute, or both derived matrices;
- text/JSON formatters: TSV-like generation matrices for terminal reading and
  schema-versioned JSON with non-finite cells normalized to `null`.

## Backend Components

- `SurrogateWorkspace`: explicit workspace facade and top-level use-case API.
- `CheckpointPredictor`: one checkpoint's validated model/schema/scaler plus
  interactive and audit inference.
- `CrossGenerationErrorAudit`: compact relative/absolute cost/rawData sum-count
  arrays and zero-inference matrix derivation.
- `PlotRequest`, `PredictionResult`, `ErrorMatrix`, and metadata dataclasses:
  immutable transfer objects between worker and UI code.
- rawData helpers: schema-specific flattening, per-item aggregate reduction,
  complete dimension description, stored-grid 0D/1D/2D slicing, coordinate-grid
  plot construction, and finite ensemble-member bounds.

## Dependency Direction

```text
app.py
  -> ui/*
  -> backend public exports

report.py
  -> backend public exports
  -> NumPy / JSON formatting

ui/*
  -> backend data contracts/facade
  -> Tkinter and Matplotlib

backend/workspace.py
  -> backend/checkpoints.py
  -> backend/rawdata.py
  -> backend/types.py
  -> installed yadof APIs

backend/checkpoints.py
  -> backend/rawdata.py
  -> backend/types.py
  -> installed yadof model/runtime APIs
```

The backend must never import UI modules. Plotting code must not parse checkpoints,
read records, or call private yadof model functions. The UI passes user intent to
the coordinator; the coordinator submits backend operations.

## Interface Invariants

- A `PredictionResult` contains reconstructed mean rawData, optional member
  samples, predicted costs, an optional real comparison, and optional off-grid
  mean/member plots. `PlotRequest` identifies the item, zero to two plot axes, and
  every fixed coordinate. `PlotData` carries selected `DimensionSpec` values,
  numeric values, and the actual fixed-coordinate label.
- Audit cost arrays have shape
  `(optimization generations, checkpoints, objectives)`.
- Audit rawData arrays have shape
  `(optimization generations, checkpoints, rawData items)`.
- An `ErrorMatrix` is two-dimensional with axis labels matching its generation
  tuples.
- Public viewer-backend imports continue through
  `yadof.tools.surrogate_viewer.backend`, even when implementation files move
  inside that package. Convenience exports at the viewer root load this backend
  lazily.
- Terminal output carries complete immutable report payloads only; progress never
  contaminates stdout and report formatting never mutates an audit.
