# 4+1 Process View

One call resolves the workspace, freezes finalized segment names plus the current
parameter definition and `calc_cost.py`, then processes each frozen ZIP once.
Manifest checks, NPZ decode/schema validation, normalization, and current-cost
recalculation are one streamed pass; invalid candidates become row issues while
readable siblings continue. It then validates display rows and builds a text summary.
Plotting is optional. When selected, numerical analysis prepares Pareto,
generation, smoothing, and hypervolume series before Matplotlib writes one PNG.

The calculation progress callback is caller-owned and advances over actually
decoded candidates. Its total is unknown while the one-pass stream is still
discovering candidates, then closes as the exact final candidate count. The CLI
renders this on stderr; another caller may translate the same callback into GUI
state without changing the analysis pipeline or adding a pre-scan of the ZIPs.
