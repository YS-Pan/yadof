"""Headless contracts for the Windows GUI's command boundaries."""

from __future__ import annotations

import os
import importlib.metadata
from pathlib import Path
import queue
import subprocess

import pytest

from yadof.tools import condor_gui


def test_installed_gui_launcher_is_packaged() -> None:
    import yadof

    assert (Path(__file__).resolve().parents[1] / "condor_gui.pyw").is_file()
    assert (Path(yadof.__file__).parent / "tools" / "condor_gui.pyw").is_file()
    assert any(
        entry.name == "yadof-gui" and entry.value == "yadof.tools.condor_gui:main"
        for entry in importlib.metadata.entry_points(group="gui_scripts")
    )


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
    ]
    with pytest.raises(ValueError):
        condor_gui.optimization_command("python.exe", workspace, -1, 3)
    with pytest.raises(ValueError):
        condor_gui.optimization_command("python.exe", workspace, 0, 0)


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
    app.stopping = True
    app._log = lambda message: None

    app._drain_events()
    assert app.stopping
    assert app.start_button.state == "disabled"

    app.events.put(("stopped", "removed"))
    app._drain_events()
    assert not app.stopping
    assert app.start_button.state == "normal"


def test_failure_lines_uses_time_tool_rows(monkeypatch) -> None:
    from yadof.tools import view_time

    monkeypatch.setattr(view_time, "build_rows", lambda workspace: [
        {"failed": False},
        {"failed": True, "event_time": "now", "job_name": "j1",
         "error_type": "timeout", "error_message": "exceeded"},
    ])
    assert condor_gui.failure_lines(Path("C:/study")) == ["now  j1  timeout  exceeded"]


def test_failure_lines_is_empty_before_any_timing_record(monkeypatch) -> None:
    from yadof.tools import view_time

    def no_rows(workspace):
        raise view_time.ViewTimeError("No recorded timing rows found in recorded_data")

    monkeypatch.setattr(view_time, "build_rows", no_rows)
    assert condor_gui.failure_lines(Path("C:/study")) == []


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
