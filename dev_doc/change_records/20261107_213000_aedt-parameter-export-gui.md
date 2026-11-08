# 2026-11-07 - Double-click AEDT parameter exporter

## Context

The user requested a `.pyw` desktop script that reads optimization variables and
bounds from AEDT text, writes `parameters_constraints.py` beside that project,
and backs up any previous file to a configurable directory defaulting to
`parameters_backup` beside the script.

## Change

- Added root `aedt_parameters_gui.pyw`, which selects the sibling installed
  development environment when present and opens the packaged HFSS parameter GUI.
  The source distribution carries this launcher; implementation stays under
  `src/yadof/`. Direct module launch is also available.
- Added editable project/backup paths, native browse dialogs, read-only variable
  preview and an explicit export button. Worker file operations report results to
  the Tk thread, disable conflicting controls and prevent closing during a write.
- Added strict project-based preview and export APIs without workspace setup or
  simulator fallback. Export creates a fresh current-format module with empty
  constraints and preserves old custom code byte for byte in its backup.
- Corrected inline `oa(...)` matching so sensitivity and tuning attributes cannot
  override optimization inclusion or bounds. Added BOM/continuation handling,
  finite-bound validation, discrete/integer values and duplicate-name diagnostics.
- Shared atomic publication between the workspace CLI and project exporter:
  compile without executing, stage and flush unique temporary content, exclusively
  create and flush a unique backup, then replace. Backup or publication failure
  preserves the previous output; failed staging is removed.

## Rationale And Impact

The existing parser and renderer already own the yadof parameter contract. Keeping
the GUI thin avoids a separate copy of those rules. The workspace CLI retains
confirmation, configured output/history locations, template preservation and
PyAEDT fallback. The new GUI instead follows the user's explicit project-adjacent
output and script-adjacent default backup requirements, without opening a solver.
The GUI states that generated constraints start empty; users can recover prior
task-specific constraints from the backup.

The bounded automatic redundancy review found that backup collision handling
first searched for a free name and then separately retried exclusive creation.
In `parameter_extraction.py`, one exclusive-creation loop now owns both naming
and race handling (4 lines added, 13 removed in that cleanup). Existing sequential
collision behavior and backup exclusivity remain; the repeated-timestamp test
checks retained bytes. Publication and cleanup safety boundaries remain separate.

User documentation, architecture and relevant blueprints describe both paths.
Default backups and generated acceptance evidence are ignored by Git.

The shared installed environment was concurrently advanced to 0.8.0 by another
GUI task. Final runtime integration therefore uses an isolated copy of that
verified 0.8.0 source baseline and adds only this exporter's files/documentation.
The extraction files were verified identical to this checkout's HEAD before
replacement. Existing 0.8.0 GUI code, documentation and version are preserved;
this task does not change the checkout's version or the private MSI runtime.

## Validation

- Built and force-installed the wheel into `D:\.venv`; verified imports originate
  below that environment's `Lib/site-packages/yadof`.
- Focused installed-package parser, export, GUI and task-CLI tests: 46 passed.
- Full regression: 674 passed, one skipped and one fast-worker crash/replacement
  test failed while importing `yadof.workspace`. Another background test/install
  workflow was concurrently using and replacing the canonical `.venv` package;
  the observed import failure coincided with that replacement. A separate regular
  wheel installation below `temp/aedt-parameters/acceptance-env/` then passed all
  47 focused checks, including that failed test and the final backup-loop cleanup.
  No source injection or editable installation was used.
- Read three existing AEDT projects: 17, 29 and 24 enabled variables. Exported only
  disposable copies below `temp/aedt-parameters/real-files/`, loaded each generated
  module and checked exact backup bytes. Original projects/task files were intact.
- Windows file association launched the root `.pyw` from a different working
  directory and exposed the expected GUI window. Screenshot verification was
  unavailable: capture and its recovery attempt both timed out.
