# 4+1 Scenarios

## CLI plot

The CLI calls `cost_viewer.view_cost`, renders progress on stderr, prints the
returned report on stdout, and prints the saved path.

## Python summary

A caller passes `output_path=None`, receives summary text and `None`, and does not
load Matplotlib.

## Future GUI

The unified GUI starts work outside its event loop, supplies a progress callback,
and consumes either the public rows/analysis functions or the `view_cost` result.
The cost viewer remains unaware of widgets and threads.

## Partial bad history

Row-local issues are collected and reported while valid display rows continue;
the operation fails only when no plottable row remains or core history cannot be
read.
