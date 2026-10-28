# 2026-10-15 09:46 - Install the double-click GUI entry with the wheel

## Context

The user wants the GUI entry available immediately after installing yadof. The
selected workflow places a `.pyw` entry in the installed environment, without a
separate installation wrapper or a manual Desktop setup step. Windows file
associations may point at a different Python, so importing yadof directly through
that interpreter could select an unrelated installed distribution.

## Change

- Added the portable installed launcher under `src/yadof/tools/condor_gui.pyw`.
  Hatch wheel shared-scripts also publishes it in `.data/scripts/`, which normal
  pip installation places beside `yadof-gui.exe` in the environment's `Scripts/`.
- On Windows the launcher invokes this exact neighboring executable and forwards
  arguments and exit status. The package copy resolves the same Scripts location
  from global/venv or user-site layouts. Missing entries fail rather than
  selecting a different environment. Non-Windows Python invocation calls the
  installed GUI main directly.
- Removed the mapping that packaged the machine-specific root launcher as the
  installed launcher. The root launcher remains the local D-drive development
  entry; installed entries require neither that file nor a fixed drive.
- Both installed `.pyw` copies remain pip-managed files, so reinstall updates
  them and uninstall removes them. This workflow adds no Desktop shortcut and
  does not initialize or mutate a workspace.
- Updated quick-start, installed user instructions, physical/development views,
  and package/tools/tests blueprints. Corrected the package blueprint's stale
  public version reference to the current 0.6.0.

## Validation

- Built a regular wheel without source injection and force-reinstalled it into
  `D:\.venv`; verified the installed yadof origin and the Scripts `.pyw` file.
- Launched the actual D-drive Scripts entry through
  `C:\ProgramData\miniconda3\envs\yadof\pythonw.exe` with `--help`; the process probe
  confirmed `D:\.venv\Scripts\pythonw.exe` and D-drive site-packages as the final
  interpreter and package origin.
- Real pip integration builds and installs a wheel in a provisioned temporary
  environment with Unicode and spaces, deletes the input wheel, then invokes both
  installed launcher copies through another environment's `python.exe` and
  `pythonw.exe`. A process-start probe records the actual interpreter and package
  origin, verifying both belong to the selected installation. Pip uninstall
  removes the Scripts entry.
- Headless contracts also cover global/venv/user-site resolution, refusal to use
  an unrelated ancestor environment, and exact argument/exit-code forwarding.
- Installed-wheel focused checks: **50 passed**. Full regression: **643 passed**
  in 185.10 seconds, with two existing scikit-learn GP convergence warnings.
- Bounded automatic-toDo review found no additional in-scope recording,
  configuration-ownership, or release-marker migration needed. The replaced
  machine-specific wheel inclusion and superseded installer wrapper are removed.

All disposable acceptance data lives below ignored `temp/`. Changes are
uncommitted; unrelated local edits and existing workspaces are preserved.
