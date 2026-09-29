# 2026-09-29 08:58 - Move Condor GUI launcher to repository root

## Context

The GUI's `.pyw` launcher was inside the package source tree, making it awkward to
find and double-click from the checkout. The nearby `src/yadof/workspace/` package
directory could also be mistaken for a user task workspace.

## Change

- Move the thin `condor_gui.pyw` entry point to the repository root while keeping
  its implementation in `src/yadof/tools/condor_gui.py`.
- Include the root launcher in source distributions and map it to the prior
  `yadof/tools/condor_gui.pyw` wheel path.
- Update the installed-package tests, source layout, and user workspace guidance.

## Rationale

The root file is easy to open in a source checkout. Its import of the installed
entry point keeps GUI behavior and framework code under `src/yadof/`.

## Impact

The root launcher requires a `.pyw` association to an environment with yadof
installed. The installed `yadof-gui` script and wheel launcher path are retained.
Task models and workflows still belong to a separate initialized workspace.

## Verification

The wheel and source distribution include the launcher at their documented paths;
18 installed-wheel package and GUI tests passed after the move. A Windows shell-open
of the root `.pyw` started the installed environment's `pythonw.exe` successfully.
