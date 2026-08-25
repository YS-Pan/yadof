# Module Blueprint: Plotting And Style

`plotting.py` lazily selects Matplotlib's `Agg` backend and writes the static PNG.
All objective costs and arithmetic average cost share the left axis. The right
axis shows a translucent fill between current-generation and cumulative
all-individual hypervolume. Generation annotations distinguish the plotted groups.

`style.py` centralizes current presentation constants. Their exact values, artist
types, legend copy, and annotation positions may change without being treated as a
data or API compatibility break. Cost/time views should remain visually coherent,
but do not require identical constants when their data needs differ.
