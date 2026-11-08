"""Double-click to export AEDT optimization parameters using installed yadof."""

from pathlib import Path
import subprocess
import sys


def main() -> int:
    script = Path(__file__).resolve()
    # Match this checkout's canonical installed-package development environment.
    runtime = script.parent.parent / ".venv" / "Scripts" / "pythonw.exe"
    try:
        if runtime.is_file() and Path(sys.executable).resolve().parent != runtime.parent:
            return subprocess.call([str(runtime), str(script), *sys.argv[1:]])
        import runpy
        import yadof

        installed = Path(yadof.__file__).parent / "tools/user_tools/aedt_parameters_gui.pyw"
        return runpy.run_path(str(installed))["main"](script_dir=script.parent)
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "AEDT 参数工具无法启动",
            "请使用安装了当前 yadof 的 Python 环境启动此脚本。\n\n" + str(exc),
            parent=root,
        )
        root.destroy()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
