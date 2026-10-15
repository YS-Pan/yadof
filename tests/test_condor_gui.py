"""Headless contracts for the Windows GUI's command boundaries."""

from __future__ import annotations

import os
import importlib.metadata
import runpy
from datetime import datetime
from pathlib import Path
import queue
import subprocess
from types import SimpleNamespace

import pytest

from yadof.tools import condor_gui


def test_checkout_launcher_prefers_adjacent_workspace(tmp_path, monkeypatch) -> None:
    launcher = Path(__file__).resolve().parents[1] / "condor_gui.pyw"
    gui_args = runpy.run_path(str(launcher))["_gui_args"]
    project = tmp_path / "project"
    workspace = project / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert gui_args([], project / "condor_gui.pyw") == ["--workspace", str(workspace)]
    assert gui_args(["--workspace", "C:/other"], project / "condor_gui.pyw") == [
        "--workspace", "C:/other",
    ]
    assert gui_args([], tmp_path / "condor_gui.pyw") == []


def test_installed_gui_launcher_is_packaged() -> None:
    import yadof

    assert (Path(__file__).resolve().parents[1] / "condor_gui.pyw").is_file()
    assert (Path(yadof.__file__).parent / "tools" / "condor_gui.pyw").is_file()
    assert any(
        entry.name == "yadof-gui" and entry.value == "yadof.tools.condor_gui:main"
        for entry in importlib.metadata.entry_points(group="gui_scripts")
    )


@pytest.mark.parametrize("location", ("checkout", "parent"))
def test_checkout_launcher_redirects_to_relative_environment(tmp_path, monkeypatch, location):
    import sys

    source = Path(__file__).resolve().parents[1] / "condor_gui.pyw"
    launcher = tmp_path / "checkout/condor_gui.pyw"
    launcher.parent.mkdir()
    launcher.write_bytes(source.read_bytes())
    environment = (launcher.parent if location == "checkout" else tmp_path) / ".venv"
    interpreter = environment / ("Scripts/pythonw.exe" if os.name == "nt" else "bin/python")
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    workspace = tmp_path / "study with spaces"
    monkeypatch.setattr(sys, "executable", str(tmp_path / "other" / "pythonw.exe"))
    monkeypatch.setattr(sys, "argv", [str(launcher), "--workspace", str(workspace)])
    launches = []
    monkeypatch.setattr(subprocess, "call", lambda command: launches.append(command) or 7)

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(launcher), run_name="__main__")

    assert exited.value.code == 7
    assert launches == [[
        str(interpreter.resolve()), str(launcher.resolve()),
        "--workspace", str(workspace),
    ]]


def test_checkout_launcher_prefers_project_environment_and_keeps_current_python_as_fallback(tmp_path):
    import sys

    source = Path(__file__).resolve().parents[1] / "condor_gui.pyw"
    select_python = runpy.run_path(str(source))["_gui_python"]
    launcher = tmp_path / "checkout/condor_gui.pyw"
    assert select_python(launcher) == Path(sys.executable).resolve()
    interpreters = [
        parent / ".venv" / ("Scripts/pythonw.exe" if os.name == "nt" else "bin/python")
        for parent in (launcher.parent, tmp_path)
    ]
    for interpreter in interpreters:
        interpreter.parent.mkdir(parents=True)
        interpreter.touch()
    assert select_python(launcher) == interpreters[0].resolve()


def test_parse_status_converts_disk_and_preserves_machine() -> None:
    rows = condor_gui.parse_status(
        "slot1@host\thost\tIdle\t8\t16384\t1048576\tundefined\n"
        "slot1_1@host\thost\tBusy\t2\t4096\t2048\t1.5\n"
    )
    assert [row.machine for row in rows] == ["host", "host"]
    assert rows[0].display == ("slot1@host", "Idle", "8", "16,384", "1,024", "—")
    assert rows[1].disk_mb == "2"
    assert rows[1].cpus_usage == "1.5"


def test_optimization_command_validates_generation_range() -> None:
    workspace = Path("C:/study")
    assert condor_gui.optimization_command("python.exe", workspace, 5, 3) == [
        "python.exe", "-m", "yadof", "run", "--workspace", str(workspace),
        "--start-generation", "5", "--generations", "3",
        "--smoke-test",
    ]
    with pytest.raises(ValueError):
        condor_gui.optimization_command("python.exe", workspace, -1, 3)
    with pytest.raises(ValueError):
        condor_gui.optimization_command("python.exe", workspace, 0, 0)


@pytest.mark.parametrize("smoke_test", (True, False))
def test_start_passes_smoke_checkbox_selection_to_run_cli(smoke_test, monkeypatch) -> None:
    from yadof.cli import build_parser

    launches = []
    workspace = Path("C:/study with spaces")
    app = object.__new__(condor_gui.CondorGUI)
    app._workspace = lambda: workspace
    app.start_var = SimpleNamespace(get=lambda: "2")
    app.generations_var = SimpleNamespace(get=lambda: "3")
    app.smoke_var = SimpleNamespace(get=lambda: smoke_test)
    app.process = None
    app.running = app.stopping = app.initializing = app.clearing = app.viewing = False
    app.start_button = SimpleNamespace(configure=lambda **kwargs: None)
    app.workspace_entry = app.workspace_button = app.init_button = app.clear_button = app.start_button
    app.view_buttons = []
    progress_settings = []
    progress_labels = []
    app.generation_bar = SimpleNamespace(configure=lambda **kwargs: progress_settings.append(kwargs))
    app.progress_var = SimpleNamespace(set=progress_labels.append)
    app.state_var = SimpleNamespace(set=lambda value: None)
    app._log = lambda message: None
    monkeypatch.setattr(
        condor_gui.threading, "Thread",
        lambda *, target, args, daemon: SimpleNamespace(start=lambda: launches.append(args)),
    )

    app.start()

    command, launched_workspace = launches[0]
    parsed = build_parser().parse_args(command[3:])
    assert launched_workspace == workspace
    assert Path(parsed.workspace) == workspace
    assert parsed.start_generation == 2
    assert parsed.generations == 3
    assert parsed.smoke_test is smoke_test
    assert progress_settings == [{"maximum": 1, "value": 0}]
    assert progress_labels == ["等待第 3 代（索引 2）"]


def test_gui_progress_tracks_actual_generation_output(monkeypatch, capsys) -> None:
    from yadof.evaluate_manager.api import _PopulationProgress

    monkeypatch.setenv("YADOF_PROGRESS", "1")
    first = _PopulationProgress(total=3, mode="distributed", generation_index=0, phase="evaluation")
    first.start()
    first.complete(2, successful=True)
    second = _PopulationProgress(total=2, mode="distributed", generation_index=1, phase="evaluation")
    second.start()
    lines = capsys.readouterr().err.splitlines()

    assert [condor_gui.parse_generation_progress(line) for line in lines] == [
        condor_gui.GenerationProgress(0, 0, 3),
        condor_gui.GenerationProgress(0, 1, 3),
        condor_gui.GenerationProgress(1, 0, 2),
    ]
    assert condor_gui.parse_generation_progress("[yadof] smoke (distributed) [#] 1/1") is None

    app = object.__new__(condor_gui.CondorGUI)
    app.events = queue.Queue()
    for line in lines:
        app.events.put(("log", line))
    bar_updates = []
    labels = []
    app.generation_bar = SimpleNamespace(configure=lambda **kwargs: bar_updates.append(kwargs))
    app.progress_var = SimpleNamespace(set=labels.append)
    app._log = lambda line: None
    app.root = SimpleNamespace(after=lambda delay, callback: None)

    app._drain_events()

    assert bar_updates == [
        {"maximum": 3, "value": 0},
        {"maximum": 3, "value": 1},
        {"maximum": 2, "value": 0},
    ]
    assert labels[-1] == "第 2 代（索引 1） · 已完成 0/2 个"


def test_query_and_drain_use_condor_commands_without_shell() -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        if command[0] == "condor_status":
            return subprocess.CompletedProcess(command, 0, "slot1@host\thost\tIdle\t1\t1024\t1024\t0\n", "")
        return subprocess.CompletedProcess(command, 0, "started", "")

    assert condor_gui.query_status(run=fake_run)[0].name == "slot1@host"
    assert condor_gui.drain_machine("host", run=fake_run) == "started"
    assert calls == [condor_gui.STATUS_COMMAND, ("condor_drain", "-graceful", "host")]


def test_stop_always_runs_condor_rm_all() -> None:
    calls = []

    class Process:
        pid = 123

        def poll(self):
            return None

        def terminate(self):
            calls.append(("terminate",))

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, "done", "")

    assert "done" in condor_gui.stop_optimization(Process(), run=fake_run)
    assert calls[-1] == ("condor_rm", "-all")
    if os.name == "nt":
        assert calls[0] == ("taskkill", "/PID", "123", "/T", "/F")
    else:
        assert calls[0] == ("terminate",)


def test_stop_reports_condor_rm_failure() -> None:
    class Process:
        def poll(self):
            return 0

    def fake_run(command, **kwargs):
        assert command == ["condor_rm", "-all"]
        return subprocess.CompletedProcess(command, 1, "", "permission denied")

    with pytest.raises(RuntimeError, match="permission denied"):
        condor_gui.stop_optimization(Process(), run=fake_run)


def test_stop_attempts_condor_rm_after_process_stop_error() -> None:
    calls = []

    class Process:
        pid = 123

        def poll(self):
            return None

        def terminate(self):
            raise OSError("termination failed")

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        if command[0] == "taskkill":
            raise OSError("termination failed")
        return subprocess.CompletedProcess(command, 0, "removed", "")

    with pytest.raises(RuntimeError, match="termination failed"):
        condor_gui.stop_optimization(Process(), run=fake_run)
    assert calls[-1] == ("condor_rm", "-all")


def test_run_exit_waits_for_condor_rm_before_reenabling_start() -> None:
    class Widget:
        state = None

        def configure(self, *, state):
            self.state = state

        def set(self, value):
            pass

        def after(self, delay, callback):
            pass

    app = object.__new__(condor_gui.CondorGUI)
    app.events = queue.Queue()
    app.events.put(("run_finished", 1))
    app.start_button = Widget()
    app.stop_button = Widget()
    app.state_var = Widget()
    app.root = Widget()
    app.process = object()
    app.running = True
    app.initializing = app.clearing = app.viewing = False
    app.stopping = True
    app.workspace_entry = Widget()
    app.workspace_button = Widget()
    app.init_button = Widget()
    app.clear_button = Widget()
    app.view_buttons = []
    app._log = lambda message: None

    app._drain_events()
    assert app.stopping
    assert app.start_button.state == "disabled"

    app.events.put(("stopped", "removed"))
    app._drain_events()
    assert not app.stopping
    assert app.start_button.state == "normal"


@pytest.fixture
def workspace_gui(tmp_path, monkeypatch):
    import tkinter as tk
    from tkinter import messagebox
    from yadof.workspace.init import init_workspace

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")
    root.withdraw()
    workspace = tmp_path / "study with spaces"
    init_workspace(workspace)
    monkeypatch.setattr(condor_gui, "query_status", lambda: [])
    monkeypatch.setattr(
        messagebox, "showerror", lambda title, message, **kwargs: pytest.fail(message),
    )
    app = condor_gui.CondorGUI(root, workspace)
    try:
        yield app, workspace
    finally:
        root.destroy()


@pytest.fixture
def synchronous_gui_workers(monkeypatch):
    monkeypatch.setattr(
        condor_gui, "threading", SimpleNamespace(
            Thread=lambda *, target, args=(), daemon: SimpleNamespace(start=lambda: target(*args)),
        ),
    )


def test_workspace_button_selects_directory_without_init_and_cancel_keeps_selection(workspace_gui, monkeypatch):
    from tkinter import filedialog

    app, workspace = workspace_gui
    selected = workspace.parent / "新工作区 with spaces"
    selected.mkdir()
    retained = selected / "notes.txt"
    retained.write_text("keep", encoding="utf-8")
    selections = iter((str(selected), ""))
    dialogs = []

    def choose(**kwargs):
        dialogs.append(kwargs)
        return next(selections)

    monkeypatch.setattr(filedialog, "askdirectory", choose)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("ran a command while selecting"))
    monkeypatch.setattr(condor_gui, "threading", SimpleNamespace(
        Thread=lambda **kwargs: pytest.fail("started a worker while selecting"),
    ))

    app.workspace_button.invoke()

    assert app.workspace_var.get() == str(selected)
    assert not app.initializing
    assert set(selected.iterdir()) == {retained}
    assert retained.read_text(encoding="utf-8") == "keep"
    assert str(app.workspace_button["text"]) == "选择文件夹…"
    assert str(app.init_button["text"]) == "初始化 workspace"
    assert str(app.clear_button["text"]) == "清空 workspace"
    assert str(app.init_button["state"]) == "normal"
    app.workspace_button.invoke()
    assert app.workspace_var.get() == str(selected)
    assert dialogs[0]["mustexist"] is True
    assert dialogs[1]["initialdir"] == str(selected)
    assert set(selected.iterdir()) == {retained}


def test_init_button_runs_init_on_selected_directory_without_chooser(
    workspace_gui, monkeypatch, synchronous_gui_workers,
):
    from tkinter import filedialog

    app, workspace = workspace_gui
    selected = workspace.parent / "新工作区 with spaces"
    selected.mkdir()
    app.workspace_var.set(str(selected))
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: pytest.fail("opened directory chooser"))
    commands = []
    real_run = subprocess.run

    def run(command, **kwargs):
        commands.append(command)
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    app.init_button.invoke()
    assert app.initializing
    assert app.workspace_var.get() == str(selected)
    assert all(str(widget["state"]) == "disabled" for widget in (
        app.workspace_entry, app.workspace_button, app.init_button, app.clear_button, app.start_button,
        *app.view_buttons,
    ))
    app._drain_events()
    assert not app.initializing
    assert app.workspace_var.get() == str(selected)
    assert commands == [[condor_gui._console_python(), "-m", "yadof", "init", str(selected)]]
    assert all((selected / name).is_file() for name in (
        ".yadof/workspace.json", "config.py", "submit/optimization.py", "job_template/workflow.py",
    ))
    assert condor_gui.load_config(selected).workspace.root == selected
    assert str(app.start_button["state"]) == "normal"
    assert str(app.init_button["state"]) == "normal"


def test_init_button_is_idempotent_and_preserves_history(workspace_gui, synchronous_gui_workers):
    app, workspace = workspace_gui
    config = workspace / "config.py"
    config.write_text(config.read_text(encoding="utf-8") + "\n# User customization\n", encoding="utf-8")
    retained = workspace / "jobs/retained.txt"
    retained.parent.mkdir()
    retained.write_text("keep history", encoding="utf-8")
    originals = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}

    app.init_button.invoke()
    app._drain_events()

    assert not app.initializing
    assert app.workspace_var.get() == str(workspace)
    assert {path: path.read_bytes() for path in originals} == originals
    assert "Workspace already initialized" in app.log.get("1.0", "end")


def test_init_button_conflict_keeps_selected_directory(workspace_gui, synchronous_gui_workers):
    app, workspace = workspace_gui
    selected = workspace.parent / "conflicting study"
    selected.mkdir()
    config = selected / "config.py"
    config.write_text("user file", encoding="utf-8")
    errors = []
    app._error = errors.append
    app.workspace_var.set(str(selected))

    app.init_button.invoke()
    app._drain_events()

    assert not app.initializing
    assert app.workspace_var.get() == str(selected)
    assert "config.py" in errors[0]
    assert config.read_text(encoding="utf-8") == "user file"
    assert not (selected / ".yadof/workspace.json").exists()
    assert str(app.workspace_button["state"]) == "normal"
    assert str(app.init_button["state"]) == "normal"


@pytest.mark.parametrize("selection", ("", "  "))
def test_init_button_requires_selected_path(workspace_gui, monkeypatch, selection):
    app, workspace = workspace_gui
    app.workspace_var.set(selection)
    errors = []
    app._error = errors.append
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("initialized an implicit path"))

    app.init_button.invoke()

    assert errors == ["请先选择文件夹"]
    assert not app.initializing
    assert app.workspace_var.get() == selection


@pytest.mark.parametrize("operation", ("start", "clear_workspace", "view"))
def test_uninitialized_selection_requires_explicit_init(workspace_gui, monkeypatch, operation):
    from tkinter import messagebox

    app, workspace = workspace_gui
    selected = workspace.parent / "empty study"
    selected.mkdir()
    app.workspace_var.set(str(selected))
    errors = []
    app._error = errors.append
    monkeypatch.setattr(messagebox, "askyesno", lambda *args, **kwargs: pytest.fail("offered cleanup"))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("initialized implicitly"))

    if operation == "view":
        app.view("cost")
    else:
        getattr(app, operation)()

    assert "初始化 workspace" in errors[0]
    assert not tuple(selected.iterdir())
    assert not app.initializing
    assert app.workspace_var.get() == str(selected)


@pytest.mark.parametrize("failure", (
    SimpleNamespace(returncode=1, stdout="init failed"),
    SimpleNamespace(returncode=3, stdout=""),
    OSError("interpreter unavailable"),
))
def test_init_worker_reports_cli_and_launch_errors(monkeypatch, failure):
    app = object.__new__(condor_gui.CondorGUI)
    app.events = queue.Queue()

    def run(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(subprocess, "run", run)
    app._init_worker(Path("D:/study with spaces"))

    kind, detail = app.events.get_nowait()
    assert kind == "init_error"
    assert detail == (str(failure) if isinstance(failure, Exception) else (
        failure.stdout or f"退出码 {failure.returncode}"
    ))


@pytest.mark.parametrize("confirm", (False, True))
def test_clear_button_requires_confirmation_and_resets_campaign(
    workspace_gui, monkeypatch, confirm, synchronous_gui_workers,
):
    from tkinter import messagebox

    app, workspace = workspace_gui
    artifacts = (
        "jobs/j1/result.txt", "recorded_data/segments/old.zip",
        "recorded_data/metadata/surrogate_training/old.json",
        "recorded_data/extra.txt", ".yadof/surrogate/checkpoints/old/model.npz",
        ".yadof/optimization/program-completion.json",
    )
    for name in artifacts:
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old evidence", encoding="utf-8")
    protected = ("config.py", "submit/optimization.py", "job_template/workflow.py", ".yadof/workspace.json")
    originals = {name: (workspace / name).read_bytes() for name in protected}
    app.start_var.set("12")
    app.generation_bar.configure(maximum=10, value=7)
    app.progress_generation_index = 12
    dialogs = []
    monkeypatch.setattr(messagebox, "askyesno", lambda title, text, **kwargs: (
        dialogs.append((text, kwargs)) or confirm
    ))

    app.clear_button.invoke()

    assert str(workspace) in dialogs[0][0]
    assert "代理训练记录" in dialogs[0][0]
    assert dialogs[0][1]["default"] == messagebox.NO
    if confirm:
        assert app.clearing
        for button in (app.start_button, app.workspace_button, app.init_button, app.clear_button):
            assert str(button["state"]) == "disabled"
        app._drain_events()
        assert not app.clearing
        assert app.start_var.get() == "0"
        assert app.progress_generation_index is None
        assert app.generation_bar["value"] == 0
        assert not tuple((workspace / "jobs").iterdir())
        assert not tuple((workspace / "recorded_data").iterdir())
        assert all(not (workspace / name).exists() for name in artifacts)
        assert str(app.start_button["state"]) == "normal"
    else:
        assert app.start_var.get() == "12"
        assert all((workspace / name).is_file() for name in artifacts)
    assert {name: (workspace / name).read_bytes() for name in protected} == originals


@pytest.mark.parametrize("phase", ("running", "stopping", "initializing", "clearing", "viewing"))
def test_workspace_actions_are_blocked_during_other_operations(workspace_gui, monkeypatch, phase):
    from tkinter import filedialog, messagebox

    app, workspace = workspace_gui
    setattr(app, phase, True)
    app._update_workspace_controls()
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: pytest.fail("opened directory chooser"))
    monkeypatch.setattr(messagebox, "askyesno", lambda *args, **kwargs: pytest.fail("offered cleanup"))
    errors = []
    app._error = errors.append
    app.browse()
    app.initialize_workspace()
    app.clear_workspace()
    app.start()
    assert len(errors) == 3
    assert app.workspace_var.get() == str(workspace)
    assert all(str(widget["state"]) == "disabled" for widget in (
        app.workspace_entry, app.workspace_button, app.init_button, app.clear_button, app.start_button,
    ))


def test_clear_refuses_active_external_campaign_and_restores_controls(
    workspace_gui, monkeypatch, synchronous_gui_workers,
):
    from tkinter import messagebox
    from yadof.recorded_data.campaign_lock import CampaignLock

    app, workspace = workspace_gui
    retained = workspace / "jobs/retained.txt"
    retained.parent.mkdir()
    retained.write_text("keep", encoding="utf-8")
    app.start_var.set("8")
    lock = CampaignLock(workspace / ".yadof/campaign.lock")
    lock.acquire()
    errors = []
    app._error = errors.append
    monkeypatch.setattr(messagebox, "askyesno", lambda *args, **kwargs: True)
    try:
        app.clear_workspace()
        app._drain_events()
    finally:
        lock.release()
    assert "already active" in errors[0]
    assert retained.read_text(encoding="utf-8") == "keep"
    assert app.start_var.get() == "8"
    assert not app.clearing
    assert str(app.clear_button["state"]) == "normal"


def test_failure_rows_keep_worker_and_job_folder(tmp_path, monkeypatch) -> None:
    from yadof.tools import view_time

    jobs_dir = tmp_path / "custom_jobs"
    job_dir = jobs_dir / "j1"
    job_dir.mkdir(parents=True)
    monkeypatch.setattr(view_time, "build_rows", lambda workspace: [
        {"failed": False},
        {"failed": True, "event_time": datetime(2026, 9, 30, 12, 5), "job_name": "j1",
         "computer": "DESKTOP-A2091", "error_type": "timeout", "error_message": "exceeded"},
    ])
    monkeypatch.setattr(condor_gui, "load_config", lambda workspace: SimpleNamespace(
        workspace=SimpleNamespace(jobs_dir=jobs_dir),
    ))
    rows = condor_gui.failure_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0].display == (
        "2026-09-30 12:05:00.000", "DESKTOP-A2091", "j1", "timeout", "exceeded",
    )
    assert rows[0].job_dir == job_dir.resolve()


def test_failure_sort_keys_and_unsafe_job_names(tmp_path) -> None:
    moment = datetime(2026, 9, 30, 12)
    rows = [
        condor_gui.FailureRow(moment, "j2", "worker-b", "timeout", "z", None),
        condor_gui.FailureRow(moment.replace(hour=11), "j1", "Worker-A", "error", "a", None),
    ]
    assert sorted(rows, key=lambda row: condor_gui.failure_sort_key(row, "event_time")) == rows[::-1]
    assert sorted(rows, key=lambda row: condor_gui.failure_sort_key(row, "worker")) == rows[::-1]
    assert sorted(rows, key=lambda row: condor_gui.failure_sort_key(row, "job_name")) == rows[::-1]
    assert condor_gui._job_dir_for_name(tmp_path, "../outside") is None
    assert condor_gui._job_dir_for_name(tmp_path, "..") is None


def test_failure_window_sorts_every_column_and_opens_selected_job(tmp_path, monkeypatch) -> None:
    import tkinter as tk
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")
    try:
        root.geometry("1x1+2000+2000")
        job_dir = tmp_path / "jobs" / "j2"
        job_dir.mkdir(parents=True)
        rows = [
            condor_gui.FailureRow(datetime(2026, 9, 30, 10), "j1", "worker-c", "timeout", "z", None),
            condor_gui.FailureRow(datetime(2026, 9, 30, 11), "j2", "worker-a", "error", "b", job_dir),
            condor_gui.FailureRow(datetime(2026, 9, 30, 12), "j3", "worker-b", "cancelled", "a", None),
        ]
        app = object.__new__(condor_gui.CondorGUI)
        app.root, app.tk, app.ttk = root, tk, ttk
        app.state_var = tk.StringVar(master=root)
        app._log = lambda message: None
        app._error = lambda message: pytest.fail(message)
        app._show_errors(rows)
        root.update()

        def find_tree(widget):
            if isinstance(widget, ttk.Treeview):
                return widget
            for child in widget.winfo_children():
                found = find_tree(child)
                if found is not None:
                    return found
            return None

        table = find_tree(root)
        assert table is not None
        for column in condor_gui.FAILURE_COLUMNS:
            root.tk.call(table.heading(column, "command"))
            actual = [table.item(item, "values")[2] for item in table.get_children()]
            expected = [row.job_name for row in sorted(rows, key=lambda row: condor_gui.failure_sort_key(row, column))]
            assert actual == expected
            root.tk.call(table.heading(column, "command"))
            assert [table.item(item, "values")[2] for item in table.get_children()] == expected[::-1]

        opened = []
        monkeypatch.setattr(condor_gui.os, "startfile", lambda path: opened.append(path), raising=False)
        root.update()
        item = next(item for item in table.get_children() if table.item(item, "values")[2] == "j2")
        x, y, _, _ = table.bbox(item)
        for _ in range(2):
            table.event_generate("<Button-1>", x=x + 4, y=y + 4)
            table.event_generate("<ButtonRelease-1>", x=x + 4, y=y + 4)
        root.update()
        assert opened == [job_dir]
    finally:
        root.destroy()


def test_failure_rows_are_empty_before_any_timing_record(monkeypatch) -> None:
    from yadof.tools import view_time

    def no_rows(workspace):
        raise view_time.ViewTimeError("No recorded timing rows found in recorded_data")

    monkeypatch.setattr(view_time, "build_rows", no_rows)
    assert condor_gui.failure_rows(Path("C:/study")) == []


@pytest.mark.parametrize("kind", ("cost", "time"))
def test_view_worker_calls_existing_tool_api(kind, monkeypatch) -> None:
    import matplotlib
    from yadof.tools import cost_viewer, view_time

    calls = []

    def fake_view(workspace, *, output_path):
        calls.append((workspace, output_path))
        return "summary", Path("C:/study/output.png")

    monkeypatch.setattr(matplotlib, "use", lambda backend: calls.append(("backend", backend)))
    monkeypatch.setattr(cost_viewer, "view_cost", fake_view)
    monkeypatch.setattr(view_time, "view_time", fake_view)
    app = object.__new__(condor_gui.CondorGUI)
    app.events = queue.Queue()
    workspace = Path("C:/study")

    app._view_worker(kind, workspace)

    event, payload = app.events.get_nowait()
    assert event == "view"
    assert payload == (kind, "summary", Path("C:/study/output.png"))
    assert calls[0] == ("backend", "Agg")
    assert calls[1][0] == workspace
    assert calls[1][1].startswith(f"{kind}_")
