# Module Blueprint: History And Analysis

`history.py` is the only adapter for the frozen recorded-data snapshot, optimization
metadata, and objective names. It opens one package-owned task interpreter for the
complete streamed read, receives every segment while its ZIP is open once, and
combines rawData decode/schema validation, normalization, and current-cost
calculation before validating numeric finiteness, objective width, and finite
arithmetic average at the original row index. Progress advances by decoded candidate
count; the total remains unknown until the streamed pass can publish its exact final
count, avoiding a separate manifest scan.

`analysis.py` owns Pareto membership, visible selection, generation grouping,
event locations, smoothing, scatter scaling, and fixed-reference minimization
hypervolume. Rows outside the normalized unit cube do not contribute to HV;
cumulative and current-generation indicator calls receive nondominated points only.
Analysis functions do not draw, print, or write files.
