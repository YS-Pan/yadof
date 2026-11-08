# Cost Viewer Project Blueprint

## Intent

Provide one reusable package for dynamic historical-cost inspection, independent
of terminal or future GUI presentation shells.

## Modules

- [Application](10_modules/application.md)
- [History and analysis](10_modules/backend.md)
- [Reporting](10_modules/reporting.md)
- [Plotting and style](10_modules/plotting.md)
- [Developer documentation](10_modules/dev_doc.md)
- [Tests](10_modules/tests.md)

## Invariants

- Read current costs from public recorded-data/task APIs; never persist them as
  authoritative history.
- Preserve the public `view_cost(...) -> (summary, optional_path)` contract.
- Keep import-time paths free of GUI frameworks and eager Matplotlib backend
  selection.
- Keep numerical/domain decisions out of terminal and GUI presentation layers.
- Resolve relative output paths under the selected workspace tool-output folder.
