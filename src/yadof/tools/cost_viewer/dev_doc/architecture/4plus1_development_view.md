# 4+1 Development View

The package is organized by responsibility rather than interface technology.
Data adaptation, numerical analysis, text reporting, and plotting can therefore
be tested and reused independently. The public `cost_viewer` package is the new
integration point; the flat `view_cost.py` module remains intentionally small.

A future GUI belongs outside this package, under the unified `yadof.gui` boundary.
GUI code may call these public functions, but GUI widget state and event loops must
not move into cost-viewer analysis or reporting modules.
