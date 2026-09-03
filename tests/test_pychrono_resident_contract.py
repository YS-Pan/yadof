"""Resident external-runtime tests use a fake physical kernel, never PyChrono."""

import runpy
import shutil
import sys

import numpy as np
import psutil
import pytest

from yadof.resources import adapter_resource


@pytest.fixture
def resident(tmp_path):
    resource = adapter_resource("chrono_com.py")
    shutil.copy2(resource, tmp_path / "chrono_com.py")
    worker = tmp_path / "kernel.py"
    worker.write_text('''import json, os, time
import numpy as np
from chrono_com import resident_worker_main, PyChronoSimulationError
CALLS = 0
def simulate(request):
    global CALLS
    CALLS += 1
    x = request["parameters"]["assigned"]["x"]
    if x == -1: raise PyChronoSimulationError("physical_failure", "impossible geometry")
    if x == -2: os._exit(23)
    if x == -3: time.sleep(30)
    if x == -4: raise TypeError("task programming defect")
    if x == -5: return {"bad.npz": {"values": np.array(1)}}, {}
    os.write(1, b"native stdout is diagnostic\\n")
    if x == 99: os.write(2, b"X" * 200000)
    values = np.array([x, x*x], dtype=np.float64)
    return {"response.npz": {"values": values, "metadata": np.asarray(json.dumps({
        "schema_version": 1, "shape": [2], "rawdata_name": "response"}))}}, {
        "pid": os.getpid(), "calls": CALLS, "pythonpath": "PYTHONPATH" in os.environ}
if __name__ == "__main__": raise SystemExit(resident_worker_main(simulate))
''', encoding="utf-8")
    adapter = runpy.run_path(str(resource))
    session = adapter["PyChronoSession"](worker, scratch_root=tmp_path / "scratch",
        interpreter=sys.executable, environment={"PYTHONPATH": "must-be-removed"})
    try:
        yield adapter, session
    finally:
        session.close()


def test_external_session_reuses_runtime_aba_and_survives_physical_failure(resident):
    adapter, session = resident
    a, da = session.evaluate_rawdata({"x": 2}, timeout=5)
    _, db = session.evaluate_rawdata({"x": 3}, timeout=5)
    again, dc = session.evaluate_rawdata({"x": 2}, timeout=5)
    assert np.array_equal(a["response.npz"]["values"], again["response.npz"]["values"])
    assert da["resident_pid"] == db["resident_pid"] == dc["resident_pid"]
    assert dc["child"]["calls"] == 3 and not dc["child"]["pythonpath"]
    with pytest.raises(adapter["PyChronoSimulationError"], match="impossible geometry"):
        session.evaluate_rawdata({"x": -1}, timeout=5)
    _, after = session.evaluate_rawdata({"x": 2}, timeout=5)
    assert after["resident_pid"] == da["resident_pid"] and after["child"]["calls"] == 5
    _, noisy = session.evaluate_rawdata({"x": 99}, timeout=5)
    assert len(noisy["stderr_tail"].encode()) <= adapter["MAX_DIAGNOSTIC_BYTES"]
    assert not list(session.scratch.glob("candidate-*"))
    pid = da["resident_pid"]
    session.close()
    assert not session.scratch.exists()
    assert not psutil.pid_exists(pid)


@pytest.mark.parametrize("failure,physical", [(-2, False), (-3, True), (-4, False), (-5, False)])
def test_external_failure_classification_and_clean_replacement(resident, failure, physical):
    adapter, session = resident
    _, before = session.evaluate_rawdata({"x": 1}, timeout=5)
    expected = adapter["PyChronoSimulationError"] if physical else adapter["PyChronoError"]
    with pytest.raises(expected) as error:
        session.evaluate_rawdata({"x": failure}, timeout=.2 if failure == -3 else 5)
    assert isinstance(error.value, adapter["PyChronoSimulationError"]) is physical
    _, after = session.evaluate_rawdata({"x": 1}, timeout=5)
    assert after["resident_pid"] != before["resident_pid"]
    assert after["child"]["calls"] == 1


def test_resident_long_scratch_has_no_external_junction(resident, tmp_path):
    adapter, original = resident
    root = tmp_path
    while len(str(root)) < 300:
        root = root / ("long-task-scratch-" * 3)
    with adapter["PyChronoSession"](original.worker, scratch_root=root, interpreter=sys.executable) as session:
        payload, diagnostics = session.evaluate_rawdata({"x": 2}, timeout=5)
        assert np.array_equal(payload["response.npz"]["values"], np.array([2., 4.]))
        assert session.launch_alias is None
        assert diagnostics["resident_pid"]
    assert not list(root.iterdir())
