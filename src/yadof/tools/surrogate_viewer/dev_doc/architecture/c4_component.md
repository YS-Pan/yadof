# C4 components

## Application Components

- `SurrogateViewerApp`: root lifecycle, workspace loading, executor submission,
  serial-based stale-result suppression, UI callback draining, cancellation, and
  error reporting.
- `InteractiveTab`: selectors, slider construction, keyboard behavior, debounced
  request intent, selected prediction inputs, and plot selection.
- `HeatmapTab`: cost/rawData quantity mapping, error type, sampling percentage,
  progress, stop intent, last complete audit, and instant matrix selection.
- `InteractivePlot`: rawData curve, ensemble band, true overlay, and objective bar
  comparison.
- `HeatmapPlot`: non-interpolated `pcolormesh`, complete edge bounds, automatic
  rectangular aspect, annotations, colorbar, and one-line title.

## Backend Components

- `SurrogateWorkspace`: explicit workspace facade and top-level use-case API.
- `CheckpointPredictor`: one checkpoint's validated model/schema/scaler plus
  interactive and audit inference.
- `CrossGenerationErrorAudit`: compact relative/absolute cost/rawData sum-count
  arrays and zero-inference matrix derivation.
- `PredictionResult`, `ErrorMatrix`, and metadata dataclasses: immutable transfer
  objects between worker and UI code.
- rawData helpers: schema-specific flattening, per-item aggregate reduction, curve
  extraction, and ensemble statistics.

## Dependency Direction

```text
app.py
  -> ui/*
  -> backend public exports

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
  samples, predicted costs, and an optional real comparison.
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
