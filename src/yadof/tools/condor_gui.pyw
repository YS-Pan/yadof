"""Double-click entry for the GUI in this installed Python environment."""

from pathlib import Path
import os
import subprocess
import sys


def _gui_executable(launcher: Path) -> Path:
    """Find this installation's entry, including the site-packages copy."""
    launcher = launcher.resolve()
    directory = launcher.parent
    if directory.name.lower() != "scripts":
        site_packages = launcher.parents[2]
        if site_packages.name != "site-packages":
            raise FileNotFoundError("Open condor_gui.pyw from the installed Scripts directory.")
        prefix = site_packages.parent
        if prefix.name.lower() == "lib":
            prefix = prefix.parent
        directory = prefix / "Scripts"
    executable = directory / "yadof-gui.exe"
    if executable.is_file():
        return executable
    raise FileNotFoundError(
        "Cannot find this installation's yadof-gui.exe. Reinstall yadof "
        "in the Python environment containing this launcher."
    )


def main() -> int:
    if os.name == "nt":
        # The generated executable binds the GUI to its installing interpreter,
        # even when Windows opens .pyw files using a different Python.
        return subprocess.call([str(_gui_executable(Path(__file__))), *sys.argv[1:]])
    from yadof.tools.condor_gui import main as gui_main

    return gui_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
