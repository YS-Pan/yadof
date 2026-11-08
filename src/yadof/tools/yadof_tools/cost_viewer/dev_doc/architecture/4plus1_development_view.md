# 4+1 Development View

The package is organized by responsibility rather than interface technology.
Data adaptation, numerical analysis, text reporting, and plotting can therefore
be tested and reused independently. The public `cost_viewer` package is the new
integration point, including the former flat module's diagnostic exports.

The double-click GUI belongs outside this package, under `yadof_tools/_shared/`.
GUI code may call these public functions, but GUI widget state and event loops must
not move into cost-viewer analysis or reporting modules.
