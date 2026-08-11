# Module Blueprint: History And Analysis

`history.py` is the only adapter for recorded results, optimization metadata, and
objective names. It validates numeric finiteness, consistent objective width, and
finite arithmetic average while preserving original row indices.

`analysis.py` owns Pareto membership, visible selection, generation grouping,
event locations, smoothing, scatter scaling, and fixed-reference minimization
hypervolume. Rows outside the normalized unit cube do not contribute to HV.
Analysis functions do not draw, print, or write files.
