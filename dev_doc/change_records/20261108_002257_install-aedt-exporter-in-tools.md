# 2026-11-08 - Install the AEDT exporter in the GUI tools folder

## Context

The user found that the tools folder opened by the private 0.8.0 installation did
not contain the newly developed HFSS variable exporter. The earlier exporter
task installed its implementation into the separate `D:/.venv` environment and
provided a source-checkout launcher; it did not update the private MSI runtime.
The main GUI update correctly opened that private installation's tools directory,
where the exporter implementation and a folder-local launcher were absent.

## Change

- Include the existing project-based exporter, its public HFSS APIs and current
  parser/publication implementation in the private 0.8.0 wheel update.
- Add `tools/aedt_parameters_gui.pyw`, so the tool is directly discoverable and
  double-clickable after pressing **tools**. The launcher forwards to its own
  installation's Python before importing yadof and does not choose the source
  checkout or an unrelated file-association environment.
- The installed launcher defaults backups to
  `%LOCALAPPDATA%/Yadof/parameters_backup`, editable in the existing GUI. Source
  checkout and direct-module defaults retain their established behavior. Runtime
  backups never belong inside installed package source.
- Preserve the 0.8.0 version, administrator tools, runtime dependencies and the
  previously installed tools button/elapsed-time implementation. Update the
  relevant user guide, architecture, blueprints and focused launcher tests.

Implementation edits remain under `src/yadof/`. Build, backup, installation and
acceptance evidence live below ignored `temp/hfss-tools-20261108/`; installed
package files are replaced through a regular wheel installation.

## Validation

- Built the isolated 0.8.0 wheel and regularly force-installed it into the
  canonical development environment. Exporter, launcher and existing Condor GUI
  focused tests passed: 98 passed.
- The private Python 3.11.15 runtime passes separate installed-entry, owning
  interpreter, default-backup, actual Tk controls, preview, export and exact
  previous-byte backup checks using only a disposable text fixture. No existing
  AEDT project, solver or optimization campaign was executed.
- The private installation was replaced through pip with dependencies and bytecode
  compilation disabled. All 832 package members match the built wheel. The
  previous GUI module, 0.8.0 distribution metadata and dependency declarations
  remain identical; runtime changes are confined to the exporter implementation,
  its HFSS public exports and the new launcher.
- A fresh system-site test environment could not collect the full suite because
  it lacked the optional scikit-learn dependency. Full regression uses the
  dependency-complete canonical environment instead, after installation has
  finished, avoiding the earlier overlapping-install failure mode. It passed all
  696 tests; the only warnings are the existing Gaussian-process convergence
  diagnostics. The JUnit report remains in the acceptance evidence directory.
