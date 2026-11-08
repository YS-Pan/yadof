# C4 Container

`yadof.tools.yadof_tools.cost_viewer` is one source package and ships with its local developer
documentation. Its stable package exports cover orchestration, row construction,
analysis, reporting, and rendering. Its package root is the single import surface;
`yadof.cli` owns terminal parsing and progress, while the sibling desktop coordinator
owns workspace selection, worker lifecycle and opening the returned PNG.

Matplotlib and Pymoo are used only inside the analysis/rendering operations that
need them; importing the CLI or the package does not select a graphical backend.
