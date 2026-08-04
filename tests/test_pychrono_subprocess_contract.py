from __future__ import annotations

import json
import os
import runpy
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import psutil
import pytest

from yadof.job_template import validate_rawdata_item
from yadof.resources import adapter_resource


def _write_fake_worker(path: Path) -> None:
    path.write_text(
        r'''from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from chrono_com import worker_main


def write_rawdata(rawdata_dir, value):
    metadata = {
        "schema_version": 1,
        "rawdata_name": "response",
        "shape": [],
        "axes": [],
        "unit": "m",
    }
    target = rawdata_dir / "response.npz"
    temporary = target.with_name(target.name + ".part")
    with temporary.open("wb") as stream:
        np.savez(
            stream,
            values=np.asarray(value, dtype=np.float64),
            metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
        )
    os.replace(temporary, target)


def simulate(request, rawdata_dir):
    mode = request.get("task_context", {}).get("mode", "success")
    if mode == "large_stderr":
        sys.stderr.write("large-stderr-start\n" + ("X" * 200000) + "\nlarge-stderr-end\n")
        sys.stderr.flush()
    if mode == "crash":
        os._exit(17)
    if mode == "handled_error":
        raise RuntimeError("fake simulation failed")
    if mode == "wait":
        marker = request["task_context"]["marker"]
        pid_file = Path(request["task_context"]["pid_file"])
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", marker]
        )
        pid_file.write_text(str(descendant.pid), encoding="utf-8")
        time.sleep(60)
    write_rawdata(rawdata_dir, request["parameters"]["assigned"]["x"])
    return {
        "cwd": os.getcwd(),
        "temp": os.environ.get("TEMP"),
        "tmp": os.environ.get("TMP"),
        "pythonpath_present": any(key.casefold() == "pythonpath" for key in os.environ),
        "python_no_user_site": os.environ.get("PYTHONNOUSERSITE"),
        "python_dont_write_bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
        "executable": sys.executable,
        "pid": os.getpid(),
        "yadof_loaded": "yadof" in sys.modules,
        "pychrono_loaded": "pychrono" in sys.modules,
    }


def postprocess(result_path, mode):
    if mode == "malformed_result":
        result_path.write_text('{"protocol":', encoding="utf-8")
        return
    changed_modes = {
        "protocol_mismatch",
        "escape_path",
        "missing_rawdata",
        "invalid_rawdata",
    }
    if mode not in changed_modes:
        return
    manifest = json.loads(result_path.read_text(encoding="utf-8"))
    raw_path = result_path.parent / "rawData" / "response.npz"
    if mode == "protocol_mismatch":
        manifest["protocol_version"] = 2
    elif mode == "escape_path":
        manifest["rawdata"][0]["path"] = "../escape.npz"
    elif mode == "missing_rawdata":
        raw_path.unlink()
    elif mode == "invalid_rawdata":
        metadata = {
            "schema_version": 1,
            "rawdata_name": "response",
            "shape": [],
            "axes": [],
            "unit": "m",
        }
        with raw_path.open("wb") as stream:
            np.savez(
                stream,
                values=np.asarray([1.0]),
                metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
            )
        manifest["rawdata"][0]["size_bytes"] = raw_path.stat().st_size
        manifest["rawdata"][0]["sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    result_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--request", required=True)
parser.add_argument("--result", required=True)
known, _unknown = parser.parse_known_args()
request = json.loads(Path(known.request).read_text(encoding="utf-8"))
mode = request.get("task_context", {}).get("mode", "success")
exit_code = worker_main(simulate)
if exit_code == 0:
    postprocess(Path(known.result), mode)
print("fake child completed")
raise SystemExit(exit_code)
''',
        encoding="utf-8",
    )


@pytest.fixture
def adapter(tmp_path: Path) -> SimpleNamespace:
    task_dir = tmp_path / "task files with spaces"
    task_dir.mkdir()
    copied_adapter = task_dir / "chrono_com.py"
    shutil.copyfile(adapter_resource("chrono_com.py"), copied_adapter)
    worker = task_dir / "chrono worker.py"
    _write_fake_worker(worker)
    namespace = runpy.run_path(str(copied_adapter))
    return SimpleNamespace(
        run=namespace["run_pychrono"],
        resolve=namespace["resolve_interpreter"],
        error=namespace["PyChronoError"],
        max_diagnostic_bytes=namespace["MAX_DIAGNOSTIC_BYTES"],
        worker=worker,
        scratch_root=tmp_path / "candidate scratch with spaces",
    )


def _run(
    adapter: SimpleNamespace,
    mode: str,
    *,
    value: float = 2.5,
    backend: str = "fast",
    output: Path | None = None,
    timeout: float = 5.0,
    task_context: dict[str, object] | None = None,
    cancel_requested=None,
):
    context = {"mode": mode, **(task_context or {})}
    return adapter.run(
        adapter.worker,
        {"x": value},
        scratch_root=adapter.scratch_root,
        backend=backend,
        rawdata_dir=output,
        load_rawdata=backend == "fast",
        normalized_parameters={"x": 0.25},
        task_context=context,
        environment={
            "YADOF_PYCHRONO_PYTHON": str(Path(sys.executable).resolve()),
            "PYTHONPATH": "poison import path",
        },
        timeout=timeout,
        cancel_requested=cancel_requested,
    )


def _pid_has_marker(pid: int, marker: str) -> bool:
    try:
        return marker in psutil.Process(pid).cmdline()
    except (psutil.Error, OSError):
        return False


def _assert_process_stopped(pid_file: Path, marker: str) -> None:
    descendant_pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _pid_has_marker(descendant_pid, marker):
        time.sleep(0.05)
    assert not _pid_has_marker(descendant_pid, marker)


def test_runtime_resolution_requires_explicit_absolute_executable(
    adapter: SimpleNamespace, tmp_path: Path
) -> None:
    with pytest.raises(adapter.error, match="YADOF_PYCHRONO_PYTHON") as missing:
        adapter.resolve(None, environment={})
    assert missing.value.category == "runtime_not_configured"

    with pytest.raises(adapter.error, match="absolute") as relative:
        adapter.resolve("python", environment={})
    assert relative.value.category == "runtime_invalid"

    with pytest.raises(adapter.error, match="unavailable") as absent:
        adapter.resolve(str((tmp_path / "missing.exe").resolve()), environment={})
    assert absent.value.category == "runtime_invalid"


def test_fast_success_uses_clean_environment_paths_with_spaces_and_valid_npz(
    adapter: SimpleNamespace,
) -> None:
    result = _run(adapter, "success", value=4.25)

    assert result.returncode == 0
    assert result.rawdata is not None
    assert float(result.rawdata["response.npz"]["values"]) == pytest.approx(4.25)
    diagnostics = result.manifest["diagnostics"]
    assert diagnostics["cwd"] == diagnostics["temp"] == diagnostics["tmp"]
    assert diagnostics["pythonpath_present"] is False
    assert diagnostics["python_no_user_site"] == "1"
    assert diagnostics["python_dont_write_bytecode"] == "1"
    assert diagnostics["yadof_loaded"] is False
    assert diagnostics["pychrono_loaded"] is False
    assert "fake child completed" in result.stdout_tail
    assert not result.scratch_dir.exists()
    assert tuple(adapter.scratch_root.iterdir()) == ()


def test_local_success_publishes_validated_rawdata_atomically(
    adapter: SimpleNamespace, tmp_path: Path
) -> None:
    output = tmp_path / "final rawData with spaces"
    result = _run(adapter, "success", value=7.5, backend="local", output=output)

    assert result.rawdata is None
    assert result.published_files == (output / "response.npz",)
    validated = validate_rawdata_item(result.published_files[0])
    assert float(validated["values"]) == pytest.approx(7.5)
    assert not any(path.suffix == ".part" for path in output.iterdir())


def test_large_stderr_is_bounded_without_invalidating_success(
    adapter: SimpleNamespace,
) -> None:
    result = _run(adapter, "large_stderr")

    assert result.stderr_truncated is True
    assert len(result.stderr_tail.encode("utf-8")) <= adapter.max_diagnostic_bytes
    assert result.stderr_tail.rstrip().endswith("large-stderr-end")


@pytest.mark.parametrize(
    ("mode", "category"),
    [
        ("malformed_result", "result_malformed"),
        ("protocol_mismatch", "protocol_mismatch"),
        ("escape_path", "output_path_invalid"),
        ("missing_rawdata", "rawdata_missing"),
        ("invalid_rawdata", "rawdata_invalid"),
    ],
)
def test_invalid_child_outputs_are_distinguishable(
    adapter: SimpleNamespace, mode: str, category: str
) -> None:
    with pytest.raises(adapter.error) as failure:
        _run(adapter, mode)
    assert failure.value.category == category
    assert tuple(adapter.scratch_root.iterdir()) == ()


def test_handled_error_and_unreported_crash_are_distinguishable(
    adapter: SimpleNamespace,
) -> None:
    with pytest.raises(adapter.error) as handled:
        _run(adapter, "handled_error")
    with pytest.raises(adapter.error) as crashed:
        _run(adapter, "crash")

    assert handled.value.category == "child_reported_error"
    assert handled.value.returncode == 3
    assert handled.value.manifest["error"] == {
        "code": "task_error",
        "message": "fake simulation failed",
    }
    assert crashed.value.category == "child_process_error"
    assert crashed.value.returncode == 17
    assert crashed.value.manifest is None


def test_timeout_terminates_child_process_tree(
    adapter: SimpleNamespace, tmp_path: Path
) -> None:
    marker = f"yadof-pychrono-descendant-{time.time_ns()}"
    pid_file = tmp_path / "descendant.pid"
    with pytest.raises(adapter.error) as failure:
        _run(
            adapter,
            "wait",
            timeout=0.8,
            task_context={"marker": marker, "pid_file": str(pid_file)},
        )

    assert failure.value.category == "timeout"
    _assert_process_stopped(pid_file, marker)
    assert tuple(adapter.scratch_root.iterdir()) == ()


def test_cancellation_uses_the_same_process_tree_cleanup(
    adapter: SimpleNamespace, tmp_path: Path
) -> None:
    marker = f"yadof-pychrono-cancel-{time.time_ns()}"
    pid_file = tmp_path / "cancel-descendant.pid"
    started = time.monotonic()
    with pytest.raises(adapter.error) as failure:
        _run(
            adapter,
            "wait",
            timeout=10.0,
            task_context={"marker": marker, "pid_file": str(pid_file)},
            cancel_requested=lambda: time.monotonic() - started > 0.8,
        )

    assert failure.value.category == "cancelled"
    _assert_process_stopped(pid_file, marker)


def test_concurrent_children_keep_scratch_and_evidence_isolated(
    adapter: SimpleNamespace,
) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(_run, adapter, "success", value=1.0)
        second_future = executor.submit(_run, adapter, "success", value=9.0)
        first = first_future.result()
        second = second_future.result()

    assert first.scratch_dir != second.scratch_dir
    assert first.rawdata is not None and second.rawdata is not None
    assert float(first.rawdata["response.npz"]["values"]) == pytest.approx(1.0)
    assert float(second.rawdata["response.npz"]["values"]) == pytest.approx(9.0)
    assert tuple(adapter.scratch_root.iterdir()) == ()
