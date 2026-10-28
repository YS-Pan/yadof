"""Launch the HTCondor GUI in the D-drive development environment."""

from pathlib import Path
import subprocess
import sys


GUI_PYTHON = Path(r"D:\.venv\Scripts\pythonw.exe")


def _gui_args(argv: list[str], launcher: Path) -> list[str]:
    if any(arg == "--workspace" or arg.startswith("--workspace=") for arg in argv):
        return argv
    workspace = launcher.resolve().parent / "workspace"
    if workspace.is_dir():
        return ["--workspace", str(workspace), *argv]
    return argv


if __name__ == "__main__":
    args = _gui_args(sys.argv[1:], Path(__file__))
    if Path(sys.executable).resolve().parent != GUI_PYTHON.resolve().parent:
        raise SystemExit(subprocess.call([
            str(GUI_PYTHON),
            str(Path(__file__).resolve()),
            *args,
        ]))

    from yadof.tools.condor_gui import main

    raise SystemExit(main(args))
