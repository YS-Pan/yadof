# 4+1 Process View

One call resolves the workspace, asks recorded data to normalize variables and
calculate current costs, validates display rows, then builds a text summary.
Plotting is optional. When selected, numerical analysis prepares Pareto,
generation, smoothing, and hypervolume series before Matplotlib writes one PNG.

The calculation progress callback is caller-owned. The CLI renders it on stderr;
another caller may translate the same callback into GUI state without changing
the analysis pipeline.
