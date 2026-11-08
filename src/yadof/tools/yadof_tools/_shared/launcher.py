"""Bind folder entry scripts to their installation before loading tool code."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


TOOLS = ("viewcost", "viewtime", "viewerror", "surrogateviewer")


def owning_runtime(entry: Path) -> Path:
    site = next((parent for parent in entry.resolve().parents if parent.name == "site-packages"), None)
    if site is None:
        raise FileNotFoundError("Open the .pyw entry from an installed yadof_tools folder.")
    prefix = site.parent
    if prefix.name.casefold() == "lib":
        prefix = prefix.parent
    for candidate in (prefix / "Scripts/pythonw.exe", prefix / "pythonw.exe"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Cannot find the Python runtime belonging to this yadof installation.")


def launch(entry: Path, tool: str, argv: list[str] | None = None) -> int:
    if tool not in TOOLS:
        raise ValueError(f"Unknown desktop tool: {tool}")
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        entry = entry.resolve()
        runtime = owning_runtime(entry)
        if Path(sys.executable).resolve().parent != runtime.parent:
            return subprocess.call([str(runtime), str(entry), *arguments])
        if tool == "surrogateviewer":
            from yadof.tools.yadof_tools.surrogate_viewer.app import main

            return main(arguments)
        parser = argparse.ArgumentParser(description=f"yadof {tool} desktop viewer")
        parser.add_argument("--workspace", type=Path, default=None)
        args = parser.parse_args(arguments)
        from yadof.tools.yadof_tools._shared.desktop import main

        return main(tool.removeprefix("view"), args.workspace)
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(tool, str(exc), parent=root)
        root.destroy()
        return 1
