from __future__ import annotations

from dataclasses import replace
import errno
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from yadof_benchmark.benchmark_runtime import execution, storage
from yadof_benchmark.benchmark_runtime.contracts import BenchmarkStorageError
from yadof_benchmark.benchmark_runtime.results import inspect_workspace
from test_benchmark import _baseline, _cell_result, _plan, _successful_command, _workspace

pytestmark = pytest.mark.structural


def _windows_error(code: int) -> PermissionError:
    error = PermissionError(errno.EACCES, "file is temporarily held by a reader")
    error.winerror = code
    return error


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_atomic_publication_waits_for_windows_readers(tmp_path, monkeypatch, winerror):
    target = tmp_path / "state.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    real_replace = storage.os.replace
    attempts = []
    delays = []

    def temporarily_busy(source, destination):
        attempts.append(Path(source))
        assert json.loads(Path(source).read_text(encoding="utf-8")) == {"new": True}
        assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
        if len(attempts) <= 2:
            raise _windows_error(winerror)
        real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", temporarily_busy)
    monkeypatch.setattr(storage, "time", SimpleNamespace(monotonic=lambda: 0.0, sleep=delays.append))
    storage.atomic_write_json(target, {"new": True})
    assert len(attempts) == 3 and len(set(attempts)) == 1
    assert delays == [0.01, 0.02]
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_publication_does_not_hide_permanent_windows_denial(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("old\n", encoding="utf-8")
    elapsed = [0.0]

    def advance(delay):
        elapsed[0] += delay

    def denied(*_args):
        raise _windows_error(5)

    monkeypatch.setattr(storage.os, "replace", denied)
    monkeypatch.setattr(storage, "time", SimpleNamespace(monotonic=lambda: elapsed[0], sleep=advance))
    with pytest.raises(BenchmarkStorageError, match="cannot atomically publish"):
        storage.atomic_write_text(target, "new\n")
    assert elapsed[0] == pytest.approx(2.0)
    assert target.read_text(encoding="utf-8") == "old\n"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("error", [OSError(errno.ENOSPC, "disk full"), PermissionError(errno.EACCES, "denied")])
def test_atomic_publication_does_not_retry_other_storage_errors(tmp_path, monkeypatch, error):
    target = tmp_path / "state.json"
    target.write_text("old\n", encoding="utf-8")
    attempts = []

    def denied(*_args):
        attempts.append(True)
        raise error

    monkeypatch.setattr(storage.os, "replace", denied)
    storage_time = SimpleNamespace(monotonic=lambda: 0.0, sleep=lambda _: pytest.fail("unexpected retry"))
    monkeypatch.setattr(storage, "time", storage_time)
    with pytest.raises(BenchmarkStorageError):
        storage.atomic_write_text(target, "new\n")
    assert len(attempts) == 1
    assert target.read_text(encoding="utf-8") == "old\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows rename/delete sharing contract")
def test_real_windows_reader_does_not_abort_atomic_publication(tmp_path):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    target = tmp_path / "state.json"
    target.write_text("old\n", encoding="utf-8")
    # Permit reading/writing, but deliberately omit FILE_SHARE_DELETE.
    handle = create_file(str(target), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    closed = threading.Event()
    timer = None

    def release_reader():
        close_handle(handle)
        closed.set()

    try:
        probe = tmp_path / "probe.txt"
        probe.write_text("probe\n", encoding="utf-8")
        with pytest.raises(OSError) as blocked:
            os.replace(probe, target)
        assert blocked.value.winerror in {5, 32, 33}
        timer = threading.Timer(0.2, release_reader)
        timer.start()
        storage.atomic_write_text(target, "new\n")
        assert closed.is_set()
        assert target.read_text(encoding="utf-8") == "new\n"
    finally:
        if timer is not None:
            timer.join()
        if not closed.is_set():
            release_reader()


def test_fatal_storage_error_cancels_peers_and_persists_terminal_state(tmp_path, monkeypatch):
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "fatal", strategies=("alpha", "beta", "gamma"), cell_concurrency=2)
    storage.initialize_workspace(_plan(tmp_path, workspace))
    barrier = threading.Barrier(2)
    started = []

    def command_runner(command, *, cancel_event, command_root, **kwargs):
        assert kwargs["label"] == "check"
        cell_id = command_root.parent.parent.name
        started.append(cell_id)
        barrier.wait(timeout=10)
        if cell_id == "c0001":
            raise BenchmarkStorageError("simulated state publication failure")
        assert cancel_event.wait(timeout=10)
        return replace(_successful_command(command, command_root=command_root, **kwargs), returncode=15)

    monkeypatch.setattr(execution, "run_logged", command_runner)
    with pytest.raises(BenchmarkStorageError, match="simulated state publication failure"):
        execution.execute_workspace(workspace, command_runner=command_runner,
                                    collector=lambda _, cell: _cell_result(cell, 0.2))
    assert set(started) == {"c0001", "c0002"}
    state = storage.read_json(workspace / "state.json")
    assert state["status"] == "failed" and state["finished_utc"]
    assert "simulated state publication failure" in state["execution_error"]["error"]
    assert state["cells"]["c0001"]["status"] == state["cells"]["c0002"]["status"] == "failed"
    assert state["cells"]["c0003"]["status"] == "planned"
    assert all(cell["active_command"] is None for cell in state["cells"].values())
    inspection = inspect_workspace(workspace)
    assert inspection["status"] == "failed"
    assert inspection["anomalies"][0]["scope"] == "workspace"
    assert "simulated state publication failure" in inspection["anomalies"][0]["message"]
