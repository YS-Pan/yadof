# C4 Container

`yadof.tools.cost_viewer` is one source package and ships with its local developer
documentation. Its stable package exports cover orchestration, row construction,
analysis, reporting, and rendering. `yadof.tools.view_cost` is a compatibility
facade, while `yadof.cli` owns terminal argument parsing and progress presentation.

Matplotlib and Pymoo are used only inside the analysis/rendering operations that
need them; importing the CLI or the package does not select a graphical backend.
