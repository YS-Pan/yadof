# 2026-09-29 20:44 - Anchor checkout GUI workspace to launcher

## Context

After double-clicking the checkout's `condor_gui.pyw`, the user saw
`C:\system32\workspace` in the GUI. This showed that the process working directory
was not the checkout directory, so a working-directory-based default was wrong for
this launcher.

## Change

When the launcher has an adjacent `workspace` directory and no explicit
`--workspace` argument, pass that absolute path to the GUI. Preserve explicit
arguments. A packaged launcher without an adjacent workspace leaves the GUI's
working-directory default in place.

## Impact

Double-clicking `D:\yadof_latest\condor_gui.pyw` now selects
`D:\yadof_latest\workspace` regardless of the process working directory.
