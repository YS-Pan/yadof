# 2026-10-10 14:00 - Align GUI launcher with the D-drive environment

## Context

The checkout launcher forced the Conda interpreter while development acceptance
installed updated wheels in `D:/.venv`. The Conda interpreter loaded a separate
user-site yadof installation. Consequently, a successful development update could
leave the double-click GUI on different code. The user explicitly requested that
the GUI launcher use the D-drive environment.

## Change

- `condor_gui.pyw` targets `D:\.venv\Scripts\pythonw.exe` before importing yadof.
  An initial interpreter from Windows file associations forwards the script and
  exact arguments to that executable. An interpreter already in the target's
  `Scripts/` directory enters the installed GUI without another relaunch.
- Existing workspace selection and argument forwarding remain unchanged.
- The wheel's bundled `.pyw` receives the same change through the existing resource
  mapping. The registered `yadof-gui` entry point keeps its installation environment.
- User guidance, tools blueprint and development architecture identify the aligned
  runtime. Framework GUI implementation remains under `src/yadof/`.

## Validation

- Built a regular wheel and force-reinstalled it without dependencies into
  `D:/.venv`; verified its yadof origin and byte equality between the checkout and
  installed launcher.
- A hidden real `pythonw.exe` probe reported executable
  `D:\.venv\Scripts\pythonw.exe`, prefix `D:\.venv`, and GUI module below
  `D:\.venv\Lib\site-packages\yadof`. Its source matches the checkout and includes
  the workspace-reset action.
- Running the actual checkout launcher with `--help` from the system Python 3.14
  successfully redirected and exited without opening a GUI or running optimization.
- GUI-focused tests: **27 passed**, including a regression that an unrelated
  initial Python forwards the correct executable, workspace argument and child
  exit code.
- Initial full regression: 625 passed, one existing backpressure timing test failed.
  The failure was reproduced in isolation: Windows Python 3.11 uses GetTickCount64
  with 15.625 ms resolution, so a real short wait can measure zero. The fixture now
  retains its blocked writer for two clock ticks before releasing it, preserving
  the existing blocking, publication and positive-duration assertions. Recording
  runtime is unchanged. GUI and recording recheck: **52 passed**. Final full
  installed-wheel regression: **626 passed**, with two existing sklearn
  Gaussian-process convergence warnings.

Existing running windows retain their original interpreter until closed. The next
double-click uses the D-drive environment. No optimization or history clearing was
performed in existing user workspaces; validation used disposable workspaces under
`temp/`. Changes remain uncommitted.
