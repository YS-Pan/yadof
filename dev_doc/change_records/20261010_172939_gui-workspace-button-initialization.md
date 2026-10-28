# 2026-10-10 17:29 - Initialize workspaces from the GUI setup button

## Context

The user clarified that **设定 workspace…** must execute `yadof init` to make the
chosen directory a workspace. The earlier directory-only selection left empty
folders without a workspace marker or starter files and did not satisfy that
request. The checkout launcher already targets the D-drive development environment.

## Change

- After directory selection, the GUI runs its environment's console Python with
  `-m yadof init PATH` on a background worker. Arguments preserve spaces and Unicode
  paths without shell interpolation. Captured UTF-8 output and exit status return
  through the existing Tk event queue.
- The current selection changes only after a successful exit. Cancellation,
  initialization conflicts, nonzero exits, and interpreter launch errors preserve
  the previous selection. Errors restore controls and show the CLI diagnostic.
- The GUI delegates marker publication, starter validation, no-overwrite rules,
  and existing-workspace idempotency to the existing initialization command.
  Initialization does not launch optimization or clear history.
- Workspace editing, setup, clearing, optimization startup, history views and
  closing are blocked during initialization. Worker events restore controls on
  the Tk thread.
- User guidance, the tools/tests blueprints, and component architecture describe
  initialization and selection as separate steps with success-only switching.

## Validation

- Built a regular wheel, force-reinstalled it without dependencies into
  `D:/.venv`, and ran focused acceptance against that installed distribution with
  `PYTHONPATH` removed: **51 passed** across GUI and initialization/check CLI tests.
- The button tests invoke the actual installed initialization command in disposable
  workspaces under `temp/`: empty Unicode/space paths receive the marker and starter
  files; existing workspace customization and job history survive; conflicting
  user files are retained and the current GUI workspace does not change.
- Command launch/exit failures and initialization exclusion use focused contracts.
- A hidden real `D:\.venv\Scripts\pythonw.exe` probe confirmed that the GUI loads
  from `D:\.venv\Lib\site-packages\yadof`, its initialization worker is present,
  and its source exactly matches the checkout. The initialization command selects
  `D:\.venv\Scripts\python.exe` from that GUI process.
- Full installed-wheel regression with `PYTHONPATH` removed: **632 passed**, with
  two existing sklearn Gaussian-process convergence warnings. The final documentation
  and validation record are included in the installed wheel; no runtime or test
  edits followed the successful regression.

No existing user workspace was initialized, optimized or cleared during validation.
Changes remain uncommitted.
