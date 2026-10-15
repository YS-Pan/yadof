# 2026-10-13 09:20 - Separate GUI folder selection, initialization and clearing

## Context

The user requested three independent GUI functions. The previous setup button
combined directory selection with `yadof init` and switched the selection only
after initialization succeeded. Folder browsing now needs to be usable separately
from workspace creation and confirmed history reset.

## Change

- **选择文件夹…** only opens the chooser and immediately selects its result.
  Cancellation retains the selection. It creates no files and starts no worker.
- **初始化 workspace** runs the existing installed `python -m yadof init PATH`
  command for the current path, with the GUI's own interpreter, on a worker.
  It does not open a chooser or switch directories. Existing initialization,
  no-overwrite rules, error handling and UTF-8 diagnostics remain owned by the CLI.
- **清空 workspace** retains its separate default-No confirmation and full reset.
  Initialization and selection do not clear history or start optimization.
- A shared current-path resolver allows initialization before a marker exists.
  Run, clear and views separately require the marker and direct the user to the
  initialization button when it is missing. Blank paths cannot initialize the
  process working directory implicitly.
- All three buttons join the existing operation exclusion. Worker completion
  restores controls on the Tk thread; initialization failure retains the selected
  folder.
- Updated user guidance, component architecture and tools/tests blueprints.
- Consolidated five identical synchronous-worker test setups into one fixture,
  removing about twenty lines of duplicate test scaffolding. Its replacement is
  local to the GUI module, so actual initialization subprocesses and library thread
  implementations remain exercised as before.

## Validation

- Built a regular wheel and force-reinstalled it without dependencies into
  `D:/.venv`. With `PYTHONPATH` removed, imports resolve below
  `D:\.venv\Lib\site-packages\yadof`.
- Focused installed-wheel acceptance for GUI, initialization/check CLI and history
  clearing: **63 passed**. Tests verify selection makes no files or commands,
  initialization uses the current Unicode/space path without a chooser, repeated
  initialization preserves edits/history, conflicts retain the selected directory,
  blank paths and uninitialized run/clear/view are rejected, and all three buttons
  follow operation exclusion. Existing confirmed-clear and cancellation behavior
  remains covered.
- Full installed-wheel regression: **638 passed**, with two existing sklearn
  Gaussian-process convergence warnings. No runtime or test changes followed that
  successful run.
- A hidden real `D:\.venv\Scripts\pythonw.exe` process constructed the GUI and
  confirmed the three separate button labels, a module loaded from the D-drive
  installation, exact byte equality with the checkout implementation, and the
  matching `D:\.venv\Scripts\python.exe` for initialization.
- Reviewed the diff against a pre-edit snapshot, preserving pre-existing changes;
  syntax, UTF-8 and added-line whitespace checks passed. No further in-scope
  recording, configuration-migration or release-marker mismatch was found.

Disposable test workspaces stay below the ignored root `temp/`. Final documentation
and this verification record are included in the installed wheel.

No existing user workspace is initialized, optimized or cleared for validation.
Changes remain uncommitted.
