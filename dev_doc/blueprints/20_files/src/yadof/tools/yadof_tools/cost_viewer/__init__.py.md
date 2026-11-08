# File blueprint: cost-viewer public exports

The package root exposes the current `view_cost` orchestration, row construction,
analysis, report, plotting and error types from their owning modules. It also
retains the diagnostic analysis/style names consumed by existing callers and
tests. There is one import surface under
`yadof.tools.yadof_tools.cost_viewer`; no second flat forwarding module is needed.

Imports do not select a Matplotlib backend or construct Tk widgets. Numerical,
history, reporting and plotting ownership remains below the package root; the
sibling `_shared/desktop.py` owns the desktop process and worker lifecycle.
Detailed contracts live in the cost-viewer's local developer documentation.
