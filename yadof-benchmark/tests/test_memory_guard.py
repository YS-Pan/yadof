import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from yadof_benchmark.benchmark_runtime import execution, memory_guard
from yadof_benchmark.benchmark_runtime.memory_guard import (
    BenchmarkResourceError, GIB, MemorySnapshot, ResourceCancellation,
    WindowsMemoryJob, child_environment, job_commit_budget, memory_pressure,
)
from yadof_benchmark.benchmark_runtime.storage import initialize_workspace, read_json
from yadof_benchmark import plan_workspace
from test_benchmark import _baseline, _workspace, _cell_result


def test_thread_limits_reach_fresh_child_and_spawned_descendant(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "16")
    monkeypatch.setenv("OMP_NUM_THREADS", "16")
    script = tmp_path / "threads.py"
    script.write_text(
        "import json, multiprocessing, os\n"
        "def probe(queue):\n"
        "    import numpy, scipy.linalg\n"
        "    from threadpoolctl import threadpool_info\n"
        "    queue.put({'env': os.environ['OPENBLAS_NUM_THREADS'], 'pools': threadpool_info()})\n"
        "if __name__ == '__main__':\n"
        "    context = multiprocessing.get_context('spawn')\n"
        "    queue = context.Queue()\n"
        "    process = context.Process(target=probe, args=(queue,))\n"
        "    process.start()\n"
        "    result = queue.get(timeout=15)\n"
        "    process.join(timeout=15)\n"
        "    assert process.exitcode == 0\n"
        "    result['parent_env'] = os.environ['OPENBLAS_NUM_THREADS']\n"
        "    print(json.dumps(result))\n", encoding="utf-8")
    result = execution.run_logged([sys.executable, str(script)], cwd=tmp_path,
        command_root=tmp_path / "command", label="run", timeout_seconds=30)
    assert result.returncode == 0
    data = read_json(result.stdout)
    assert data["env"] == data["parent_env"] == "1"
    assert data["pools"] and all(pool["num_threads"] == 1 for pool in data["pools"])
    assert os.environ["OPENBLAS_NUM_THREADS"] == "16"
    assert read_json(tmp_path / "command/started.json")["native_thread_limits"]["OPENBLAS_NUM_THREADS"] == "1"


def test_commit_pressure_is_detected_despite_free_physical_memory():
    snapshot = MemorySnapshot(48 * GIB, 30 * GIB, 99 * GIB, 100 * GIB)
    assert "commit" in memory_pressure(snapshot)
    assert job_commit_budget(snapshot) == 0
    stable = MemorySnapshot(48 * GIB, 30 * GIB, 25 * GIB, 100 * GIB)
    assert memory_pressure(stable) is None
    assert job_commit_budget(stable) == 55 * GIB
    assert "physical" in memory_pressure(MemorySnapshot(48 * GIB, GIB, 25 * GIB, 100 * GIB))


def test_memory_watchdog_failure_is_latched_and_cancels_peers():
    guard = ResourceCancellation(reader=lambda: MemorySnapshot(48 * GIB, 30 * GIB, 99 * GIB, 100 * GIB))
    with pytest.raises(BenchmarkResourceError, match="commit"):
        guard.check()
    assert guard.is_set()
    guard.reader = lambda: MemorySnapshot(48 * GIB, 30 * GIB, 20 * GIB, 100 * GIB)
    with pytest.raises(BenchmarkResourceError, match="commit"):
        guard.check()


def test_memory_resource_error_cancels_all_cells_without_fail_fast(tmp_path, monkeypatch):
    _baseline(tmp_path)
    root = _workspace(tmp_path / "pressure", strategies=("alpha", "beta", "gamma"),
                      cell_concurrency=2, fail_fast=False)
    initialize_workspace(plan_workspace(root, baselines_root=tmp_path / "baselines"))
    barrier, started, peer_cancelled = threading.Barrier(2), [], threading.Event()
    def command(args, *, cancel_event, command_root, **kwargs):
        cell = command_root.parent.parent.name
        started.append(cell)
        barrier.wait(timeout=10)
        if cell == "c0001":
            raise BenchmarkResourceError("simulated commit exhaustion")
        assert cancel_event.wait(timeout=10)
        peer_cancelled.set()
        raise BenchmarkResourceError("peer cancelled after commit exhaustion")
    monkeypatch.setattr(execution, "run_logged", command)
    with pytest.raises(BenchmarkResourceError, match="commit exhaustion"):
        execution.execute_workspace(root, command_runner=command, collector=lambda _, cell: _cell_result(cell, .2))
    assert peer_cancelled.is_set() and set(started) == {"c0001", "c0002"}
    state = read_json(root / "state.json")
    assert state["status"] == "failed" and state["cells"]["c0003"]["status"] == "planned"
    assert "commit exhaustion" in state["execution_error"]["error"]


@pytest.mark.skipif(os.name != "nt", reason="Windows commit and job-object contract")
def test_windows_job_limits_descendant_commit_without_exhausting_host(tmp_path):
    # The OS denies a 256 MiB commitment under a 128 MiB job limit. No host
    # exhaustion and no touching large physical allocations is needed.
    child = tmp_path / "allocate.py"
    child.write_text(
        "import ctypes, json\n"
        "kernel = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]\n"
        "kernel.VirtualAlloc.restype = ctypes.c_void_p\n"
        "address = kernel.VirtualAlloc(None, 256 * 1024**2, 0x3000, 4)\n"
        "error = ctypes.get_last_error()\n"
        "if address:\n"
        "    kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]\n"
        "    kernel.VirtualFree(address, 0, 0x8000)\n"
        "print(json.dumps({'allocation_denied': not bool(address), 'error': error}))\n", encoding="utf-8")
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import pathlib, subprocess, sys, time\n"
        "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(.01)\n"
        "raise SystemExit(subprocess.run([sys.executable, sys.argv[2]]).returncode)\n", encoding="utf-8")
    gate = tmp_path / "go"
    job = WindowsMemoryJob(128 * 1024**2)
    processes = []
    try:
        # Distinct concurrent command roots must share the same nonempty job,
        # including when the test runner itself belongs to an outer Windows job.
        for _ in range(2):
            process = subprocess.Popen([sys.executable, str(parent), str(gate), str(child)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=child_environment())
            processes.append(process)
            job.assign(process)
        gate.touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, stderr
            assert json.loads(stdout)["allocation_denied"]
        sample = memory_guard.memory_snapshot()
        assert sample.commit_limit >= sample.commit_total > 0
    finally:
        job.close()
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
