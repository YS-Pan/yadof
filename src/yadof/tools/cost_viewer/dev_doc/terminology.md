# Cost Viewer Terminology

| Term | Meaning |
|---|---|
| display row | One finite, objective-width-consistent dynamic historical result plus optional provenance annotations. |
| average cost | The arithmetic mean of every normalized objective cost in one display row. |
| visible Pareto set | At most ten nondominated display rows selected by lowest average cost for emphasis and the CLI table. |
| generation group | One contiguous sequence sharing optimization-run identity and generation index. |
| all-individual hypervolume | Hypervolume of every valid display row through a generation endpoint. |
| current-generation hypervolume | Hypervolume of only the display rows in the generation group at that endpoint. |
| hypervolume interval | The shaded right-axis area between current-generation and all-individual hypervolume; it has no drawn boundary lines. |
| compatibility facade | `yadof.tools.view_cost`, which forwards the former import surface to this package. |
