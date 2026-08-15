# 4+1 Process View

One call resolves the workspace, freezes finalized segment names plus the current
parameter definition and `calc_cost.py`, then processes each frozen ZIP once.
Manifest checks, NPZ decode/schema validation, normalization, and current-cost
recalculation are one streamed pass; invalid candidates become row issues while
readable siblings continue. It then validates display rows and builds a text summary.
Plotting is optional. When selected, numerical analysis prepares Pareto,
generation, smoothing, and hypervolume series before Matplotlib writes one PNG.

The calculation progress callback reports actually decoded candidates. Its total is
unknown while the one-pass stream is still discovering candidates, then closes as
the exact final candidate count. Its string-compatible message also carries the
separate frozen-segment position used only to fill a terminal bar. The CLI therefore
renders candidate `N/?` text beside a steadily advancing segment bar on stderr;
another caller can treat the message as ordinary text without changing the analysis
pipeline or adding a pre-scan of the ZIPs.
