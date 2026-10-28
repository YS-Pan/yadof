"""Relocatable support for the MSI-owned Python prefix, loaded by its ._pth."""

import os
from pathlib import Path
import sys


_prefix = Path(sys.executable).resolve().parent.parent
# The executable/DLL live under Scripts while the complete standard library and
# development headers live in the containing private prefix.
sys.base_prefix = sys.base_exec_prefix = str(_prefix)
_dll_handles = []
for _directory in (_prefix, _prefix / "Scripts", _prefix / "DLLs", _prefix / "Library/bin"):
    if _directory.is_dir():
        _dll_handles.append(os.add_dll_directory(str(_directory)))
for _variable, _directory in (
    ("TCL_LIBRARY", _prefix / "Library/lib/tcl8.6"),
    ("TK_LIBRARY", _prefix / "Library/lib/tk8.6"),
):
    os.environ[_variable] = str(_directory)
sys.dont_write_bytecode = True
# The GUI's child-process reader and CLI evidence use UTF-8. Isolated startup
# ignores PYTHONIOENCODING, so configure the private streams explicitly.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ._pth excludes external Python installations, including PYTHONPATH/user site.
# Prepared workflows still need their own sibling modules, like worker_misc.py.
# Add that one task directory after the private libraries, without loading .pth
# files or sitecustomize from the task or the caller's environment.
_entry = sys.argv[0] if sys.argv else ""
_task_directory = Path(_entry).resolve().parent if _entry and not _entry.startswith("-") else Path.cwd()
if str(_task_directory) not in sys.path:
    sys.path.append(str(_task_directory))
