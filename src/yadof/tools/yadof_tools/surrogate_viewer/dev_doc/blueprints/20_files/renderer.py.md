# File blueprint: renderer.py

## Responsibility

Render one inspection's selected rawData, ensemble range, recorded truth when
available, and aligned objective comparison to a PNG with Matplotlib's
`FigureCanvasAgg` boundary.

## Contracts

- Support scalar, one-dimensional curve, and two-dimensional surface selections.
- Show ensemble min/max as a scalar interval, curve band, or surface range.
- Give two-dimensional prediction and truth one shared finite color scale.
- Accept already resolved arrays/labels only; perform no workspace, selector,
  checkpoint, or inference work.
- Never import pyplot, Tkinter, `backend_tkagg`, or UI widgets and never choose an
  interactive backend.
