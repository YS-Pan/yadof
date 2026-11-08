from __future__ import annotations

import time
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

tk = pytest.importorskip("tkinter")

import yadof

gui = SimpleNamespace(**runpy.run_path(str(
    Path(yadof.__file__).parent / "tools/user_tools/aedt_parameters_gui.pyw"
)))


@pytest.fixture
def app(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    application = gui.AedtParametersApp(root, script_dir=tmp_path)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *_args, **_kwargs: None)
    yield application
    application.busy = False
    application._close()


def _wait(app):
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.busy


def _project(path: Path) -> Path:
    project = path / "项目 with spaces.aedt"
    project.write_text(
        "$begin 'OptimizationSetup1'\n$begin 'Variables'\n"
        "width(i=true, int=false, Min='1mm', Max='3mm')\n"
        "$end 'Variables'\n$end 'OptimizationSetup1'\n",
        encoding="utf-8",
    )
    return project


def test_browse_select_cancel_and_manual_entry_do_not_write_files(app, tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **_kwargs: str(project))
    app._browse_project()
    assert app.project.get() == str(project)
    assert app.output.get() == str(tmp_path / "parameters_constraints.py")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **_kwargs: "")
    app._browse_project()
    assert app.project.get() == str(project)
    app.project.set(str(tmp_path / "another.aedt"))
    assert not (tmp_path / "parameters_constraints.py").exists()
    assert not app.default_backup.exists()


def test_preview_and_export_with_default_backup_restore_controls(app, tmp_path):
    project = _project(tmp_path)
    output = tmp_path / "parameters_constraints.py"
    output.write_bytes(b"original")
    app.project.set(str(project))
    app._start("preview")
    _wait(app)
    assert len(app.variables.get_children()) == 1
    assert output.read_bytes() == b"original"
    assert not app.default_backup.exists()

    app.backup.set("")
    app._start("export")
    _wait(app)
    assert app.backup.get() == str(tmp_path / "parameters_backup")
    assert [p.read_bytes() for p in app.default_backup.iterdir()] == [b"original"]
    assert "Parameter('width', ((1, 3),), unit='mm')" in output.read_text(encoding="utf-8")
    assert all(str(control.cget("state")) == "normal" for control in app.controls)


def test_backup_chooser_and_manual_path_are_used(app, tmp_path, monkeypatch):
    backup = tmp_path / "自选 backups"
    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **_kwargs: str(backup))
    app._browse_backup()
    assert app.backup.get() == str(backup)
    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **_kwargs: "")
    app._browse_backup()
    assert app.backup.get() == str(backup)
    (tmp_path / "parameters_constraints.py").write_bytes(b"old")
    app.project.set(str(_project(tmp_path)))
    app._start("export")
    _wait(app)
    assert [p.read_bytes() for p in backup.iterdir()] == [b"old"]
    assert not app.default_backup.exists()


def test_failure_reports_error_and_restores_controls(app, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *args, **_kwargs: errors.append(args))
    app.project.set(str(tmp_path / "missing.aedt"))
    app._start("export")
    _wait(app)
    assert errors
    assert "操作失败" in app.status.get()
    assert all(str(control.cget("state")) == "normal" for control in app.controls)
    assert not app.default_backup.exists()


def test_missing_optimization_setup_preserves_old_parameter_file(app, tmp_path, monkeypatch):
    project = _project(tmp_path)
    project.write_text("VariableProp('width', 'UD', '', '2mm', oa(i=true, Min='1mm', Max='3mm'))\n", encoding="utf-8")
    output = tmp_path / "parameters_constraints.py"
    output.write_bytes(b"original")
    errors = []
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *args, **_kwargs: errors.append(args))
    app.project.set(str(project))
    app._start("export")
    _wait(app)
    assert errors and "OptimizationSetup1" in str(errors)
    assert output.read_bytes() == b"original"
    assert not app.default_backup.exists()
