# Module Blueprint: Plotting And Style

`plotting.py` lazily selects Matplotlib's `Agg` backend and writes the static PNG.
All objective costs and arithmetic average cost share the left axis. The right
axis shows only a translucent fill between current-generation and cumulative
all-individual hypervolume; no upper or lower HV boundary line is drawn.

`style.py` centralizes presentation constants. Shared cost/time visual constants
remain governed by the root tools blueprint, so changing one requires the root
alignment review even though cost constants live here.
