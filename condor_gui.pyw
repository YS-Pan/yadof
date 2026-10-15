"""Launch the installed HTCondor GUI from a source checkout."""

from pathlib import Path
import os
import subprocess
import sys


def _gui_python(launcher: Path) -> Path:
    root = launcher.resolve().parent
    interpreter = "Scripts/pythonw.exe" if os.name == "nt" else "bin/python"
    for environment in (root / ".venv", root.parent / ".venv"):
        candidate = environment / interpreter
        if candidate.is_file():
            return candidate.resolve()
    return Path(sys.executable).resolve()


def _gui_args(argv: list[str], launcher: Path) -> list[str]:
    if any(arg == "--workspace" or arg.startswith("--workspace=") for arg in argv):
        return argv
    workspace = launcher.resolve().parent / "workspace"
    if workspace.is_dir():
        return ["--workspace", str(workspace), *argv]
    return argv


if __name__ == "__main__":
    launcher = Path(__file__).resolve()
    args = _gui_args(sys.argv[1:], launcher)
    gui_python = _gui_python(launcher)
    if Path(sys.executable).resolve().parent != gui_python.parent:
        raise SystemExit(subprocess.call([
            str(gui_python), str(launcher),
            *args,
        ]))

    from yadof.tools.condor_gui import main

    raise SystemExit(main(args))
