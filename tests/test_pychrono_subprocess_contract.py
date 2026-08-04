from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

import numpy as np
import psutil
import pytest

from yadof.job_template import (
    validate_named_rawdata_items,
    validate_rawdata_item,
)


PROTOCOL = "yadof.pychrono-subprocess"
PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1_048_576
MAX_RESULT_BYTES = 262_144
MAX_DIAGNOSTIC_BYTES = 65_536


@dataclass(frozen=True)
class ContractOutcome:
    category: str
    returncode: int | None
    scratch: Path
    stdout_tail: str
    stderr_tail: str
    stdout_truncated: bool
    stderr_truncated: bool
    manifest: Mapping[str, object] | None = None
    rawdata: Mapping[str, Mapping[str, object]] | None = None


class ContractFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _resolve_interpreter(value: str | None) -> Path:
    if value is None or not value.strip():
        raise ContractFailure(
            "runtime_not_configured", "YADOF_PYCHRONO_PYTHON is not configured"
        )
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise ContractFailure(
            "runtime_invalid", "PyChrono interpreter must be an absolute file"
        )
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise ContractFailure("runtime_invalid", "PyChrono interpreter is not executable")
    return path.resolve()


def _strict_json_bytes(payload: Mapping[str, object], *, maximum: int) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractFailure("request_invalid", str(exc)) from exc
    if len(encoded) > maximum:
        raise ContractFailure("request_invalid", "encoded request exceeds limit")
    return encoded


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ContractFailure("result_missing", "child wrote no result manifest")
    encoded = path.read_bytes()
    if len(encoded) > MAX_RESULT_BYTES:
        raise ContractFailure("result_malformed", "result manifest exceeds limit")
    try:
        loaded = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractFailure("result_malformed", str(exc)) from exc
    if not isinstance(loaded, dict):
        raise ContractFailure("result_malformed", "result root must be an object")
    return loaded


def _diagnostic_tail(payload: bytes) -> tuple[str, bool]:
    truncated = len(payload) > MAX_DIAGNOSTIC_BYTES
    retained = payload[-MAX_DIAGNOSTIC_BYTES:]
    return retained.decode("utf-8", errors="replace"), truncated


def _known_descendants(root_pid: int) -> tuple[int, ...]:
    try:
        return tuple(
            process.pid
            for process in psutil.Process(root_pid).children(recursive=True)
        )
    except (psutil.Error, OSError):
        return ()


def _kill_pids(pids: tuple[int, ...]) -> None:
    processes: list[psutil.Process] = []
    for pid in dict.fromkeys(pids):
        try:
            processes.append(psutil.Process(pid))
        except (psutil.Error, OSError):
            continue
    for process in reversed(processes):
        try:
            process.kill()
        except (psutil.Error, OSError):
            continue
    if processes:
        psutil.wait_procs(processes, timeout=2.0)


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    descendants = _known_descendants(process.pid)
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    _kill_pids((*descendants, process.pid))


def _validate_manifest_identity(
    manifest: Mapping[str, object], request_id: str
) -> None:
    if (
        manifest.get("protocol") != PROTOCOL
        or manifest.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise ContractFailure("protocol_mismatch", "result protocol does not match")
    if manifest.get("request_id") != request_id:
        raise ContractFailure("request_mismatch", "result request_id does not match")


def _validate_success_rawdata(
    scratch: Path, manifest: Mapping[str, object]
) -> dict[str, Mapping[str, object]]:
    raw_entries = manifest.get("rawdata")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ContractFailure("rawdata_missing", "success listed no rawData")

    raw_dir = (scratch / "rawData").resolve()
    seen: set[str] = set()
    expected_names: set[str] = set()
    paths: list[tuple[str, Path]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            raise ContractFailure("result_malformed", "rawdata entry must be an object")
        relative_text = entry.get("path")
        if not isinstance(relative_text, str) or "\\" in relative_text:
            raise ContractFailure("output_path_invalid", "rawData path is invalid")
        relative = PurePosixPath(relative_text)
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or relative.parts[0] != "rawData"
            or relative.name in {"", ".", ".."}
            or relative.suffix.casefold() != ".npz"
        ):
            raise ContractFailure("output_path_invalid", relative_text)
        folded = relative.name.casefold()
        if folded in seen:
            raise ContractFailure("output_path_invalid", "duplicate rawData basename")
        seen.add(folded)
        expected_names.add(relative.name)
        candidate = scratch / "rawData" / relative.name
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ContractFailure("rawdata_missing", relative_text) from exc
        if (
            resolved.parent != raw_dir
            or candidate.is_symlink()
            or not resolved.is_file()
        ):
            raise ContractFailure("output_path_invalid", relative_text)
        try:
            declared_size = int(entry["size_bytes"])
            declared_hash = str(entry["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractFailure("result_malformed", "invalid rawData digest fields") from exc
        if resolved.stat().st_size != declared_size:
            raise ContractFailure("rawdata_invalid", "rawData size mismatch")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != declared_hash:
            raise ContractFailure("rawdata_invalid", "rawData digest mismatch")
        paths.append((relative.name, resolved))

    if not raw_dir.is_dir():
        raise ContractFailure("rawdata_missing", "rawData directory is absent")
    actual_entries = tuple(raw_dir.iterdir())
    if any(not entry.is_file() for entry in actual_entries):
        raise ContractFailure("rawdata_invalid", "rawData directory is not flat")
    if {entry.name for entry in actual_entries} != expected_names:
        raise ContractFailure("rawdata_invalid", "rawData contains unlisted files")

    loaded_items: dict[str, Mapping[str, object]] = {}
    try:
        for name, path in paths:
            validated = validate_rawdata_item(path)
            for key, value in validated.items():
                array = np.asarray(value)
                if array.dtype.hasobject or array.dtype.fields is not None:
                    raise ValueError(f"{name}:{key} has forbidden dtype")
                if key in {"values", "data"} or key.startswith("axis_"):
                    if array.dtype.kind not in "biuf" or not np.all(np.isfinite(array)):
                        raise ValueError(f"{name}:{key} is not finite real numeric data")
            loaded_items[name] = {
                key: np.asarray(value).copy() for key, value in validated.items()
            }
        validate_named_rawdata_items(loaded_items)
    except (OSError, ValueError, TypeError) as exc:
        raise ContractFailure("rawdata_invalid", str(exc)) from exc
    return loaded_items


def _write_fake_worker(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


PROTOCOL = "yadof.pychrono-subprocess"
VERSION = 1


def write_json_atomic(path, payload):
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_rawdata(path, value, *, invalid=False):
    metadata = {
        "schema_version": 1,
        "rawdata_name": "response",
        "shape": [1] if invalid else [],
        "axes": [],
        "unit": "m",
    }
    temporary = path.with_name(path.name + ".part")
    with temporary.open("wb") as stream:
        np.savez(
            stream,
            values=np.asarray(value, dtype=np.float64),
            metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
        )
    os.replace(temporary, path)


parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--result", required=True)
arguments = parser.parse_args()
request_path = Path(arguments.request)
result_path = Path(arguments.result)
request = json.loads(request_path.read_text(encoding="utf-8"))
request_id = request["request_id"]
mode = request.get("task_context", {}).get("mode", "success")

if mode == "large_stderr":
    sys.stderr.write("large-stderr-start\n" + ("X" * 200000) + "\nlarge-stderr-end\n")
    sys.stderr.flush()
if mode == "crash":
    os._exit(17)
if mode == "handled_error":
    write_json_atomic(
        result_path,
        {
            "protocol": PROTOCOL,
            "protocol_version": VERSION,
            "request_id": request_id,
            "status": "error",
            "rawdata": [],
            "error": {"code": "task_error", "message": "fake simulation failed"},
            "diagnostics": {},
        },
    )
    sys.exit(3)
if mode == "timeout_descendant":
    marker = request["task_context"]["marker"]
    descendant = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", marker]
    )
    Path("descendant.pid").write_text(str(descendant.pid), encoding="utf-8")
    time.sleep(60)
if mode == "malformed_result":
    result_path.write_text('{"protocol":', encoding="utf-8")
    sys.exit(0)

raw_dir = Path("rawData")
raw_dir.mkdir()
raw_path = raw_dir / "response.npz"
if mode not in {"missing_rawdata", "escape_path"}:
    write_rawdata(
        raw_path,
        request["parameters"]["assigned"]["x"],
        invalid=mode == "invalid_rawdata",
    )

rawdata_path = "../escape.npz" if mode == "escape_path" else "rawData/response.npz"
entry = {
    "path": rawdata_path,
    "size_bytes": raw_path.stat().st_size if raw_path.exists() else 0,
    "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path.exists() else "0" * 64,
}
manifest = {
    "protocol": PROTOCOL,
    "protocol_version": 2 if mode == "protocol_mismatch" else VERSION,
    "request_id": request_id,
    "status": "ok",
    "rawdata": [entry],
    "diagnostics": {
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
    },
}
write_json_atomic(result_path, manifest)
print("fake child completed")
''',
        encoding="utf-8",
    )


def _run_fake_child(
    base: Path,
    mode: str,
    *,
    value: float = 2.5,
    timeout: float = 5.0,
    marker: str | None = None,
) -> ContractOutcome:
    interpreter = _resolve_interpreter(str(Path(sys.executable).resolve()))
    worker = base / "task files with spaces" / "chrono worker.py"
    _write_fake_worker(worker)
    if not worker.is_file():
        raise ContractFailure("worker_missing", "fake child entry point is absent")

    scratch = base / "candidate scratch with spaces"
    scratch.mkdir(parents=True)
    request_id = f"fake-{time.time_ns()}"
    task_context: dict[str, object] = {"mode": mode}
    if marker is not None:
        task_context["marker"] = marker
    request_payload: dict[str, object] = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "parameters": {
            "assigned": {"x": value},
            "normalized": {"x": 0.25},
        },
        "context": {
            "backend": "local",
            "evaluation_id": request_id,
            "scratch_dir": ".",
            "rawdata_dir": "rawData",
        },
        "task_context": task_context,
    }
    request_path = scratch / "request.json"
    request_path.write_bytes(
        _strict_json_bytes(request_payload, maximum=MAX_REQUEST_BYTES)
    )
    result_path = scratch / "result.json"

    child_environment = os.environ.copy()
    for key in tuple(child_environment):
        if key.casefold() == "pythonpath":
            child_environment.pop(key)
    child_environment.update(
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(scratch.resolve()),
        TMP=str(scratch.resolve()),
    )
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            str(interpreter),
            "-u",
            str(worker.resolve()),
            "--request",
            str(request_path.resolve()),
            "--result",
            str(result_path.resolve()),
        ],
        cwd=str(scratch),
        env=child_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = process.communicate(timeout=5.0)

    stdout_tail, stdout_truncated = _diagnostic_tail(stdout)
    stderr_tail, stderr_truncated = _diagnostic_tail(stderr)
    if timed_out:
        return ContractOutcome(
            "timeout",
            None,
            scratch,
            stdout_tail,
            stderr_tail,
            stdout_truncated,
            stderr_truncated,
        )

    manifest: dict[str, object] | None = None
    try:
        manifest = _read_manifest(result_path)
        _validate_manifest_identity(manifest, request_id)
    except ContractFailure as exc:
        category = "child_process_error" if process.returncode else exc.category
        return ContractOutcome(
            category,
            process.returncode,
            scratch,
            stdout_tail,
            stderr_tail,
            stdout_truncated,
            stderr_truncated,
        )

    if process.returncode != 0:
        category = (
            "child_reported_error"
            if manifest.get("status") == "error"
            and isinstance(manifest.get("error"), dict)
            else "child_process_error"
        )
        return ContractOutcome(
            category,
            process.returncode,
            scratch,
            stdout_tail,
            stderr_tail,
            stdout_truncated,
            stderr_truncated,
            manifest,
        )
    if manifest.get("status") != "ok":
        return ContractOutcome(
            "result_malformed",
            process.returncode,
            scratch,
            stdout_tail,
            stderr_tail,
            stdout_truncated,
            stderr_truncated,
            manifest,
        )
    try:
        rawdata = _validate_success_rawdata(scratch, manifest)
    except ContractFailure as exc:
        return ContractOutcome(
            exc.category,
            process.returncode,
            scratch,
            stdout_tail,
            stderr_tail,
            stdout_truncated,
            stderr_truncated,
            manifest,
        )
    return ContractOutcome(
        "success",
        process.returncode,
        scratch,
        stdout_tail,
        stderr_tail,
        stdout_truncated,
        stderr_truncated,
        manifest,
        rawdata,
    )


def _pid_has_marker(pid: int, marker: str) -> bool:
    try:
        return marker in psutil.Process(pid).cmdline()
    except (psutil.Error, OSError):
        return False


def test_runtime_resolution_requires_explicit_absolute_executable(tmp_path: Path) -> None:
    with pytest.raises(ContractFailure, match="not configured") as missing:
        _resolve_interpreter(None)
    assert missing.value.category == "runtime_not_configured"

    with pytest.raises(ContractFailure, match="absolute") as relative:
        _resolve_interpreter("python")
    assert relative.value.category == "runtime_invalid"

    with pytest.raises(ContractFailure, match="absolute") as absent:
        _resolve_interpreter(str((tmp_path / "missing.exe").resolve()))
    assert absent.value.category == "runtime_invalid"


def test_success_uses_clean_environment_paths_with_spaces_and_valid_npz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "poison import path"))
    outcome = _run_fake_child(tmp_path, "success", value=4.25)

    assert outcome.category == "success"
    assert outcome.returncode == 0
    assert outcome.rawdata is not None
    assert float(outcome.rawdata["response.npz"]["values"]) == pytest.approx(4.25)
    diagnostics = outcome.manifest["diagnostics"]  # type: ignore[index]
    assert isinstance(diagnostics, dict)
    assert diagnostics["cwd"] == str(outcome.scratch.resolve())
    assert diagnostics["temp"] == str(outcome.scratch.resolve())
    assert diagnostics["tmp"] == str(outcome.scratch.resolve())
    assert diagnostics["pythonpath_present"] is False
    assert diagnostics["python_no_user_site"] == "1"
    assert diagnostics["python_dont_write_bytecode"] == "1"
    assert diagnostics["yadof_loaded"] is False
    assert diagnostics["pychrono_loaded"] is False
    assert "fake child completed" in outcome.stdout_tail


def test_large_stderr_is_bounded_without_invalidating_success(tmp_path: Path) -> None:
    outcome = _run_fake_child(tmp_path, "large_stderr")

    assert outcome.category == "success"
    assert outcome.stderr_truncated is True
    assert len(outcome.stderr_tail.encode("utf-8")) <= MAX_DIAGNOSTIC_BYTES
    assert outcome.stderr_tail.rstrip().endswith("large-stderr-end")


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
    tmp_path: Path, mode: str, category: str
) -> None:
    outcome = _run_fake_child(tmp_path, mode)
    assert outcome.category == category
    assert outcome.rawdata is None


def test_handled_error_and_unreported_crash_are_distinguishable(tmp_path: Path) -> None:
    handled = _run_fake_child(tmp_path / "handled", "handled_error")
    crashed = _run_fake_child(tmp_path / "crashed", "crash")

    assert handled.category == "child_reported_error"
    assert handled.returncode == 3
    assert handled.manifest is not None
    assert handled.manifest["error"] == {
        "code": "task_error",
        "message": "fake simulation failed",
    }
    assert crashed.category == "child_process_error"
    assert crashed.returncode == 17
    assert crashed.manifest is None


def test_timeout_terminates_child_process_tree(tmp_path: Path) -> None:
    marker = f"yadof-pychrono-descendant-{time.time_ns()}"
    outcome = _run_fake_child(
        tmp_path,
        "timeout_descendant",
        timeout=0.8,
        marker=marker,
    )

    assert outcome.category == "timeout"
    descendant_pid = int(
        (outcome.scratch / "descendant.pid").read_text(encoding="utf-8")
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _pid_has_marker(descendant_pid, marker):
        time.sleep(0.05)
    assert not _pid_has_marker(descendant_pid, marker)


def test_concurrent_children_keep_scratch_and_evidence_isolated(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(_run_fake_child, tmp_path / "first", "success", value=1.0),
            executor.submit(_run_fake_child, tmp_path / "second", "success", value=9.0),
        )
        first, second = (future.result() for future in futures)

    assert first.category == second.category == "success"
    assert first.scratch.resolve() != second.scratch.resolve()
    assert first.rawdata is not None and second.rawdata is not None
    assert float(first.rawdata["response.npz"]["values"]) == pytest.approx(1.0)
    assert float(second.rawdata["response.npz"]["values"]) == pytest.approx(9.0)
