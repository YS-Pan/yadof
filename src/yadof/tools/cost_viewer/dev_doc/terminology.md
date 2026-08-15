# Cost Viewer Terminology

| Term | Meaning |
|---|---|
| display row | One finite, objective-width-consistent dynamic historical result plus optional provenance annotations. |
| interpretation snapshot | The per-command frozen finalized-segment list and parameter/`calc_cost.py` definition used for every display row. |
| average cost | The arithmetic mean of every normalized objective cost in one display row. |
| visible Pareto set | At most ten nondominated display rows selected by lowest average cost for emphasis and the CLI table. |
| generation group | One contiguous sequence sharing optimization-run identity and generation index. |
| all-individual hypervolume | Hypervolume of the cumulative nondominated valid display rows through a generation endpoint; excluding dominated rows preserves its value. |
| current-generation hypervolume | Hypervolume of only the display rows in the generation group at that endpoint. |
| hypervolume interval | The shaded right-axis area between current-generation and all-individual hypervolume, bounded by thin translucent polylines that connect values at generation plotting positions. |
| compatibility facade | `yadof.tools.view_cost`, which forwards the former import surface to this package. |
