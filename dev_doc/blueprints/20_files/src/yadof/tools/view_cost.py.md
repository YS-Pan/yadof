# File Blueprint: src/yadof/tools/view_cost.py

## Intent

Preserve the established `yadof.tools.view_cost` import path after the cost-view
implementation moved into the independently documented `tools/cost_viewer/`
subpackage.

## Contract

- Re-export the former public functions and `ViewCostError` from
  `yadof.tools.cost_viewer`.
- Retain existing internal analysis/style names needed by compatibility tests and
  downstream callers, without implementing those responsibilities here.
- Do not add orchestration, analysis, report, plotting, CLI, or GUI logic.
- New package and CLI integrations import `yadof.tools.cost_viewer`; this facade is
  not the growth point for future features.

The detailed current contracts live in
`src/yadof/tools/cost_viewer/dev_doc/README.md`.
