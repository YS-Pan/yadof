# Module Blueprint: Plotting And Style

`plotting.py` lazily selects Matplotlib's `Agg` backend and writes the static PNG.
All objective costs and arithmetic average cost share the left axis. The right
axis shows a translucent fill between current-generation and cumulative
all-individual hypervolume, bounded by thin translucent polylines that connect
the values at each generation plotting position. Its compact legend label is
`HV (all & current gen.)`. Generation indices use two
alternating vertical positions so dense adjacent labels remain distinguishable.

`style.py` centralizes presentation constants. Shared cost/time visual constants
remain governed by the root tools blueprint, so changing one requires the root
alignment review even though cost constants live here.
