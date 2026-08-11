# C4 Component

- `types.py` defines caller-facing type aliases and `ViewCostError`.
- `history.py` adapts dynamic recorded history and optional provenance into
  validated display rows.
- `analysis.py` owns Pareto, generation, smoothing, layout, and hypervolume
  calculations without drawing.
- `report.py` owns terminal summary and Pareto-table presentation.
- `style.py` owns cost-plot presentation constants shared by rendering and tests.
- `plotting.py` owns Matplotlib import, artists, axes, legends, and PNG output.
- `api.py` coordinates config resolution, row construction, summary generation,
  and optional plotting.
- `__init__.py` is the stable integration surface.

Dependencies flow from API/presentation toward history, analysis, types, and
style. History and analysis never import plotting or the CLI.
