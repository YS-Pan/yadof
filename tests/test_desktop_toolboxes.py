"""Installed folder entries, runtime ownership and read-only desktop dispatch."""
from pathlib import Path
import runpy
import sys
import threading
from types import SimpleNamespace

import pytest
import yadof
from yadof.tools.yadof_tools._shared import desktop, launcher


@pytest.mark.parametrize("tool", launcher.TOOLS)
def test_installed_entry_invokes_the_shared_runtime_gateway(tool, monkeypatch):
    entry = Path(yadof.__file__).parent / "tools/yadof_tools" / f"{tool}.pyw"
    assert entry.is_file()
    actual_run = runpy.run_path
    calls = []

    def load(path, *args, **kwargs):
        if Path(path).name == "launcher.py":
            return {"launch": lambda *args: calls.append(args) or 7}
        return actual_run(path, *args, **kwargs)

    monkeypatch.setattr(runpy, "run_path", load)
    with pytest.raises(SystemExit) as result:
        actual_run(str(entry), run_name="__main__")
    assert result.value.code == 7
    assert calls == [(entry.resolve(), tool)]


@pytest.mark.parametrize("runtime_path", ("Scripts/pythonw.exe", "pythonw.exe"))
def test_framework_entry_resolves_its_own_runtime(tmp_path, runtime_path):
    prefix = tmp_path / "安装 environment"
    runtime = prefix / runtime_path
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    entry = prefix / "Lib/site-packages/yadof/tools/yadof_tools/viewcost.pyw"
    assert launcher.owning_runtime(entry) == runtime


def test_framework_entry_forwards_from_an_unrelated_python(tmp_path, monkeypatch):
    runtime = tmp_path / "private/Scripts/pythonw.exe"
    entry = tmp_path / "private/Lib/site-packages/yadof/tools/yadof_tools/viewcost.pyw"
    calls = []
    monkeypatch.setattr(launcher, "owning_runtime", lambda path: runtime)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "other/pythonw.exe"))
    monkeypatch.setattr(launcher.subprocess, "call", lambda args: calls.append(args) or 3)
    assert launcher.launch(entry, "viewcost", ["--workspace", "D:/研究 with spaces"]) == 3
    assert calls == [[str(runtime), str(entry), "--workspace", "D:/研究 with spaces"]]


@pytest.mark.parametrize(("tool", "kind"), (("viewcost", "cost"), ("viewtime", "time"), ("viewerror", "error")))
def test_framework_entries_dispatch_the_selected_workspace(tool, kind, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "owning_runtime", lambda path: Path(sys.executable))
    monkeypatch.setattr(desktop, "main", lambda *args: calls.append(args) or 0)
    assert launcher.launch(Path("entry.pyw"), tool, ["--workspace", "D:/研究"]) == 0
    assert calls == [(kind, Path("D:/研究"))]


def test_surrogate_entry_dispatches_to_the_existing_application(monkeypatch):
    pytest.importorskip("matplotlib")
    from yadof.tools.yadof_tools.surrogate_viewer import app

    calls = []
    monkeypatch.setattr(launcher, "owning_runtime", lambda path: Path(sys.executable))
    monkeypatch.setattr(app, "main", lambda args: calls.append(args) or 0)
    assert launcher.launch(Path("entry.pyw"), "surrogateviewer", ["--workspace", "D:/study"]) == 0
    assert calls == [["--workspace", "D:/study"]]


def test_runtime_lookup_refuses_missing_installations(tmp_path):
    with pytest.raises(FileNotFoundError, match="installed yadof_tools"):
        launcher.owning_runtime(tmp_path / "entry.pyw")
    with pytest.raises(FileNotFoundError, match="belonging to this"):
        launcher.owning_runtime(tmp_path / "Lib/site-packages/yadof/tools/yadof_tools/viewtime.pyw")


@pytest.fixture
def tk_available():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.destroy()
    return tk


def test_workspace_chooser_cancel_creates_no_files(tmp_path, monkeypatch, tk_available):
    from tkinter import filedialog

    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: "")
    assert desktop.main("cost") == 0
    assert not tuple(tmp_path.iterdir())


def test_uninitialized_folder_is_reported_without_automatic_setup(tmp_path, monkeypatch, tk_available):
    from tkinter import messagebox

    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda *args, **kwargs: errors.append(args))
    assert desktop.main("cost", tmp_path) == 1
    assert errors and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("kind", ("cost", "time", "error"))
def test_standalone_history_view_reads_on_a_worker_and_presents_on_tk(
    tmp_path, monkeypatch, tk_available, kind,
):
    from tkinter import messagebox
    from yadof.workspace.init import init_workspace

    init_workspace(tmp_path)
    main_thread = threading.get_ident()
    workers, opened, dialogs = [], [], []

    def build(selected, workspace):
        workers.append(threading.get_ident())
        assert (selected, workspace) == (kind, tmp_path)
        return ("errors", []) if kind == "error" else ("view", (kind, "summary", tmp_path / "view.png"))

    monkeypatch.setattr(desktop, "build_view", build)
    monkeypatch.setattr(desktop.os, "startfile", lambda path: opened.append((path, threading.get_ident())), raising=False)
    monkeypatch.setattr(messagebox, "showinfo", lambda *args, **kwargs: dialogs.append(threading.get_ident()))
    monkeypatch.setattr(messagebox, "showerror", lambda *args, **kwargs: pytest.fail(str(args)))
    assert desktop.main(kind, tmp_path) == 0
    assert workers and workers[0] != main_thread
    if kind == "error":
        assert dialogs == [main_thread] and not opened
    else:
        assert opened == [(tmp_path / "view.png", main_thread)]


def test_failed_history_view_reports_error_and_exits(tmp_path, monkeypatch, tk_available):
    from tkinter import messagebox
    from yadof.workspace.init import init_workspace

    init_workspace(tmp_path)
    errors = []

    def fail(*args):
        raise RuntimeError("unreadable history")

    monkeypatch.setattr(desktop, "build_view", fail)
    monkeypatch.setattr(messagebox, "showerror", lambda *args, **kwargs: errors.append(args))
    assert desktop.main("time", tmp_path) == 1
    assert errors == [("viewtime", "unreadable history")]
