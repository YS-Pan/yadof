"""Project Chrono subprocess adapter resource.

Copy this file into a workspace before importing it from ``workflow.py`` or
``evaluation.py``.  The adapter launches the absolute interpreter selected by
``YADOF_PYCHRONO_PYTHON`` and crosses the runtime boundary only through the
versioned JSON/NPZ protocol documented by yadof.  It deliberately imports neither
PyChrono nor yadof.

A task-owned ``chrono_worker.py`` may import :func:`worker_main` from this copied
file.  Its task callback imports ``pychrono`` only after ``worker_main`` has
validated the request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path, PurePosixPath

import numpy as np


PROTOCOL = "yadof.pychrono-subprocess"
PROTOCOL_VERSION = 1
RAWDATA_SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 1_048_576
MAX_RESULT_BYTES = 262_144
MAX_DIAGNOSTIC_BYTES = 65_536
_POLL_INTERVAL_SEC = 0.05
_TERMINATION_WAIT_SEC = 5.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HANDLED_CHILD_EXIT_CODES = {2, 3, 4}


class PyChronoError(RuntimeError):
    """One stable adapter failure category plus bounded process diagnostics."""

    def __init__(
        self,
        category: str,
        message: str,
        *,
        returncode: int | None = None,
        stdout_tail: str = "",
        stderr_tail: str = "",
        stdout_truncated: bool = False,
        stderr_truncated: bool = False,
        manifest: Mapping[str, object] | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.category = str(category)
        self.message = str(message)
        self.returncode = returncode
        self.stdout_tail = str(stdout_tail)
        self.stderr_tail = str(stderr_tail)
        self.stdout_truncated = bool(stdout_truncated)
        self.stderr_truncated = bool(stderr_truncated)
        self.manifest = dict(manifest) if manifest is not None else None
        self.details = dict(details or {})
        super().__init__(f"{self.category}: {self.message}")

    def attach_process(
        self,
        *,
        returncode: int | None,
        stdout_tail: str,
        stderr_tail: str,
        stdout_truncated: bool,
        stderr_truncated: bool,
    ) -> "PyChronoError":
        self.returncode = returncode
        self.stdout_tail = stdout_tail
        self.stderr_tail = stderr_tail
        self.stdout_truncated = stdout_truncated
        self.stderr_truncated = stderr_truncated
        return self

    def as_diagnostics(self) -> dict[str, object]:
        output: dict[str, object] = {
            "category": self.category,
            "message": self.message,
            "returncode": self.returncode,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }
        if self.manifest is not None:
            output["manifest"] = dict(self.manifest)
        output.update(self.details)
        return output


@dataclass(frozen=True, slots=True)
class PyChronoResult:
    """Validated evidence and diagnostics from one completed child process."""

    request_id: str
    backend: str
    interpreter: Path
    worker: Path
    scratch_dir: Path
    returncode: int
    elapsed_sec: float
    stdout_tail: str
    stderr_tail: str
    stdout_truncated: bool
    stderr_truncated: bool
    manifest: Mapping[str, object]
    published_files: tuple[Path, ...]
    rawdata: Mapping[str, Mapping[str, object]] | None
    scratch_cleanup_error: str | None = None

    def as_diagnostics(self) -> dict[str, object]:
        child = self.manifest.get("diagnostics", {})
        output: dict[str, object] = {
            "request_id": self.request_id,
            "backend": self.backend,
            "interpreter": str(self.interpreter),
            "worker": str(self.worker),
            "returncode": self.returncode,
            "elapsed_sec": self.elapsed_sec,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "rawdata_files": [path.name for path in self.published_files]
            if self.published_files
            else sorted(self.rawdata or {}),
            "child": dict(child) if isinstance(child, Mapping) else {},
        }
        if self.scratch_cleanup_error:
            output["scratch_cleanup_error"] = self.scratch_cleanup_error
        return output


def resolve_interpreter(
    configured: str | Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the explicit PyChrono interpreter without PATH or parent fallback."""

    selected_environment = os.environ if environment is None else environment
    raw_value = configured
    if raw_value is None:
        raw_value = selected_environment.get("YADOF_PYCHRONO_PYTHON")
    if raw_value is None or not str(raw_value).strip():
        raise PyChronoError(
            "runtime_not_configured",
            "set YADOF_PYCHRONO_PYTHON to the absolute PyChrono interpreter",
        )
    path = Path(str(raw_value).strip())
    if not path.is_absolute():
        raise PyChronoError(
            "runtime_invalid", "PyChrono interpreter path must be absolute"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PyChronoError(
            "runtime_invalid", f"PyChrono interpreter is unavailable: {path}"
        ) from exc
    if not resolved.is_file():
        raise PyChronoError(
            "runtime_invalid", f"PyChrono interpreter is not a file: {resolved}"
        )
    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise PyChronoError(
            "runtime_invalid", f"PyChrono interpreter is not executable: {resolved}"
        )
    return resolved


def build_request(
    assigned_parameters: Mapping[str, object],
    *,
    backend: str,
    normalized_parameters: Mapping[str, object] | None = None,
    evaluation_id: str | None = None,
    request_id: str | None = None,
    task_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build and validate one version-1 JSON request object."""

    selected_backend = str(backend).strip().lower()
    if selected_backend not in {"fast", "local", "distributed"}:
        raise PyChronoError(
            "request_invalid", "backend must be fast, local, or distributed"
        )
    selected_request_id = str(request_id or uuid.uuid4().hex).strip()
    selected_evaluation_id = str(evaluation_id or selected_request_id).strip()
    if not selected_request_id or not selected_evaluation_id:
        raise PyChronoError(
            "request_invalid", "request_id and evaluation_id must be non-empty"
        )
    if not isinstance(assigned_parameters, Mapping):
        raise PyChronoError(
            "request_invalid", "assigned_parameters must be a mapping"
        )
    assigned = _parameter_mapping(assigned_parameters, normalized=False)
    normalized = (
        None
        if normalized_parameters is None
        else _parameter_mapping(normalized_parameters, normalized=True)
    )
    if task_context is not None and not isinstance(task_context, Mapping):
        raise PyChronoError("request_invalid", "task_context must be a mapping")

    parameters: dict[str, object] = {"assigned": assigned}
    if normalized is not None:
        parameters["normalized"] = normalized
    payload: dict[str, object] = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": selected_request_id,
        "parameters": parameters,
        "context": {
            "backend": selected_backend,
            "evaluation_id": selected_evaluation_id,
            "scratch_dir": ".",
            "rawdata_dir": "rawData",
        },
        "task_context": dict(task_context or {}),
    }
    encoded = _encode_json(payload, maximum=MAX_REQUEST_BYTES, category="request_invalid")
    return _decode_json(encoded, maximum=MAX_REQUEST_BYTES, category="request_invalid")


def run_pychrono(
    worker: str | Path,
    assigned_parameters: Mapping[str, object],
    *,
    scratch_root: str | Path,
    backend: str,
    rawdata_dir: str | Path | None = None,
    load_rawdata: bool = False,
    normalized_parameters: Mapping[str, object] | None = None,
    evaluation_id: str | None = None,
    task_context: Mapping[str, object] | None = None,
    interpreter: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: float | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> PyChronoResult:
    """Launch one isolated child and publish validated file or memory rawData.

    Fast callers set ``load_rawdata=True`` and receive a named in-memory mapping.
    Local/distributed callers pass their final flat ``rawdata_dir``.  The adapter
    creates and removes one unique child scratch below ``scratch_root``.
    """

    selected_backend = str(backend).strip().lower()
    if selected_backend == "fast":
        if not load_rawdata or rawdata_dir is not None:
            raise PyChronoError(
                "request_invalid",
                "fast mode requires load_rawdata=True and no rawdata_dir",
            )
    elif selected_backend in {"local", "distributed"}:
        if load_rawdata or rawdata_dir is None:
            raise PyChronoError(
                "request_invalid",
                "local/distributed mode requires rawdata_dir and load_rawdata=False",
            )
    else:
        raise PyChronoError(
            "request_invalid", "backend must be fast, local, or distributed"
        )

    worker_path = _resolved_worker(worker)
    child_environment = _child_environment(environment)
    interpreter_path = resolve_interpreter(
        interpreter, environment=child_environment
    )
    timeout_value = _timeout_value(timeout)
    request = build_request(
        assigned_parameters,
        backend=selected_backend,
        normalized_parameters=normalized_parameters,
        evaluation_id=evaluation_id,
        task_context=task_context,
    )
    request_id = str(request["request_id"])
    root = _scratch_root(scratch_root, interpreter_path)
    scratch = Path(tempfile.mkdtemp(prefix="pychrono-", dir=root)).resolve()
    request_path = scratch / "request.json"
    result_path = scratch / "result.json"
    stdout_path = scratch / "stdout.bin"
    stderr_path = scratch / "stderr.bin"
    process: subprocess.Popen[bytes] | None = None
    started = time.monotonic()
    process_values: dict[str, object] = {
        "returncode": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
    }

    try:
        _write_bytes_atomic(
            request_path,
            _encode_json(
                request, maximum=MAX_REQUEST_BYTES, category="request_invalid"
            ),
        )
        launch_environment = _child_environment(environment, scratch=scratch)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
                process = subprocess.Popen(
                    [
                        str(interpreter_path),
                        "-u",
                        str(worker_path),
                        "--request",
                        str(request_path),
                        "--result",
                        str(result_path),
                    ],
                    cwd=str(scratch),
                    env=launch_environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    start_new_session=os.name != "nt",
                    creationflags=creationflags,
                )
                stop_category = _wait_for_process(
                    process,
                    timeout=timeout_value,
                    cancel_requested=cancel_requested,
                )
                if stop_category is not None:
                    _terminate_process_tree(process)
                    try:
                        process.wait(timeout=_TERMINATION_WAIT_SEC)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=_TERMINATION_WAIT_SEC)
        except PyChronoError:
            raise
        except OSError as exc:
            raise PyChronoError(
                "launch_failed",
                f"could not start PyChrono child with {interpreter_path}: {exc}",
            ) from exc

        stdout_tail, stdout_truncated = _file_tail(stdout_path)
        stderr_tail, stderr_truncated = _file_tail(stderr_path)
        process_values.update(
            returncode=None if process is None else int(process.returncode),
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
        if stop_category is not None:
            raise PyChronoError(
                stop_category,
                "PyChrono child was cancelled"
                if stop_category == "cancelled"
                else f"PyChrono child exceeded timeout={timeout_value:g} seconds",
            )

        returncode = int(process.returncode)
        if returncode != 0:
            manifest = _optional_error_manifest(result_path, request_id)
            if (
                returncode in _HANDLED_CHILD_EXIT_CODES
                and manifest is not None
                and manifest.get("status") == "error"
                and isinstance(manifest.get("error"), Mapping)
            ):
                child_error = dict(manifest["error"])
                raise PyChronoError(
                    "child_reported_error",
                    str(child_error.get("message") or "PyChrono child reported an error"),
                    manifest=manifest,
                    details={"child_error": child_error},
                )
            raise PyChronoError(
                "child_process_error",
                f"PyChrono child exited with return code {returncode}",
                manifest=manifest,
            )

        manifest = _read_result_manifest(result_path)
        _validate_manifest_identity(manifest, request_id)
        if manifest.get("status") != "ok":
            raise PyChronoError(
                "result_malformed", "exit-zero result status must be 'ok'"
            )
        child_diagnostics = manifest.get("diagnostics")
        if not isinstance(child_diagnostics, Mapping):
            raise PyChronoError(
                "result_malformed", "result diagnostics must be an object"
            )
        source_paths, payloads = _validated_manifest_rawdata(scratch, manifest)

        published: tuple[Path, ...] = ()
        memory: Mapping[str, Mapping[str, object]] | None = None
        if selected_backend == "fast":
            memory = payloads
        else:
            assert rawdata_dir is not None
            published = _publish_rawdata(
                source_paths,
                rawdata_dir,
                forbidden_root=scratch,
                runtime_prefix=_runtime_prefix(interpreter_path),
            )
        elapsed = time.monotonic() - started
        result = PyChronoResult(
            request_id=request_id,
            backend=selected_backend,
            interpreter=interpreter_path,
            worker=worker_path,
            scratch_dir=scratch,
            returncode=returncode,
            elapsed_sec=elapsed,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            manifest=manifest,
            published_files=published,
            rawdata=memory,
        )
    except PyChronoError as exc:
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        exc.attach_process(
            returncode=process_values["returncode"],  # type: ignore[arg-type]
            stdout_tail=str(process_values["stdout_tail"]),
            stderr_tail=str(process_values["stderr_tail"]),
            stdout_truncated=bool(process_values["stdout_truncated"]),
            stderr_truncated=bool(process_values["stderr_truncated"]),
        )
        cleanup_error = _remove_scratch(scratch)
        if cleanup_error:
            exc.details["scratch_cleanup_error"] = cleanup_error
        raise
    except OSError as exc:
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        category = "launch_failed" if process is None else "rawdata_invalid"
        failure = PyChronoError(category, f"adapter filesystem operation failed: {exc}")
        failure.attach_process(
            returncode=process_values["returncode"],  # type: ignore[arg-type]
            stdout_tail=str(process_values["stdout_tail"]),
            stderr_tail=str(process_values["stderr_tail"]),
            stdout_truncated=bool(process_values["stdout_truncated"]),
            stderr_truncated=bool(process_values["stderr_truncated"]),
        )
        cleanup_error = _remove_scratch(scratch)
        if cleanup_error:
            failure.details["scratch_cleanup_error"] = cleanup_error
        raise failure from exc

    cleanup_error = _remove_scratch(scratch)
    if cleanup_error:
        result = PyChronoResult(
            request_id=result.request_id,
            backend=result.backend,
            interpreter=result.interpreter,
            worker=result.worker,
            scratch_dir=result.scratch_dir,
            returncode=result.returncode,
            elapsed_sec=result.elapsed_sec,
            stdout_tail=result.stdout_tail,
            stderr_tail=result.stderr_tail,
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
            manifest=result.manifest,
            published_files=result.published_files,
            rawdata=result.rawdata,
            scratch_cleanup_error=cleanup_error,
        )
    return result


def worker_main(
    simulate: Callable[[Mapping[str, object], Path], Mapping[str, object] | None],
    argv: Sequence[str] | None = None,
) -> int:
    """Validate a child request, run task mechanics, and publish one result.

    ``simulate(request, rawdata_dir)`` is task-owned.  It imports PyChrono, writes
    direct schema-compatible NPZ files below ``rawdata_dir``, and may return a small
    JSON diagnostics mapping.  This helper imports neither PyChrono nor yadof.
    """

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    try:
        arguments = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code or 2)
    request_path = Path(arguments.request)
    result_path = Path(arguments.result)
    request_id = ""
    request: dict[str, object] | None = None
    try:
        _validate_worker_paths(request_path, result_path)
        request = _decode_json(
            _read_bounded(request_path, MAX_REQUEST_BYTES, "request_invalid"),
            maximum=MAX_REQUEST_BYTES,
            category="request_invalid",
        )
        _validate_request_document(request)
        request_id = str(request["request_id"])
    except (PyChronoError, OSError) as exc:
        message = exc.message if isinstance(exc, PyChronoError) else str(exc)
        _write_worker_error(result_path, request_id, "request_error", message)
        return 2

    rawdata_dir = result_path.parent / "rawData"
    try:
        if rawdata_dir.exists():
            raise PyChronoError(
                "rawdata_invalid", "child rawData directory already exists"
            )
        rawdata_dir.mkdir()
        diagnostics = simulate(request, rawdata_dir)
        if diagnostics is None:
            diagnostics = {}
        if not isinstance(diagnostics, Mapping):
            raise TypeError("simulate() diagnostics must be a mapping or None")
    except Exception as exc:
        traceback.print_exc()
        _write_worker_error(result_path, request_id, "task_error", str(exc))
        return 3

    try:
        paths, _payloads = _validated_rawdata_directory(rawdata_dir)
        entries = [
            {
                "path": f"rawData/{path.name}",
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in paths
        ]
        manifest: dict[str, object] = {
            "protocol": PROTOCOL,
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "status": "ok",
            "rawdata": entries,
            "diagnostics": dict(diagnostics),
        }
        _write_json_atomic(result_path, manifest, maximum=MAX_RESULT_BYTES)
    except Exception as exc:
        traceback.print_exc()
        _write_worker_error(result_path, request_id, "publication_error", str(exc))
        return 4
    return 0


def _parameter_mapping(
    source: Mapping[str, object], *, normalized: bool
) -> dict[str, object]:
    output: dict[str, object] = {}
    for raw_name, value in source.items():
        name = str(raw_name)
        if not name.strip():
            raise PyChronoError(
                "request_invalid", "parameter names must be non-empty strings"
            )
        if normalized:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise PyChronoError(
                    "request_invalid", f"normalized parameter {name!r} must be numeric"
                )
            numeric = float(value)
            if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                raise PyChronoError(
                    "request_invalid",
                    f"normalized parameter {name!r} must be finite in [0, 1]",
                )
            output[name] = numeric
        else:
            output[name] = value
    return output


def _encode_json(
    payload: Mapping[str, object], *, maximum: int, category: str
) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PyChronoError(category, f"JSON encoding failed: {exc}") from exc
    if len(encoded) > maximum:
        raise PyChronoError(category, f"encoded JSON exceeds {maximum} bytes")
    return encoded


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _decode_json(encoded: bytes, *, maximum: int, category: str) -> dict[str, object]:
    if len(encoded) > maximum:
        raise PyChronoError(category, f"encoded JSON exceeds {maximum} bytes")
    try:
        loaded = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PyChronoError(category, f"invalid UTF-8 JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PyChronoError(category, "JSON document root must be an object")
    return loaded


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(
    path: Path, payload: Mapping[str, object], *, maximum: int
) -> None:
    _write_bytes_atomic(
        path,
        _encode_json(payload, maximum=maximum, category="result_malformed"),
    )


def _read_bounded(path: Path, maximum: int, category: str) -> bytes:
    if not path.is_file():
        raise PyChronoError(category, f"required file is missing: {path}")
    if path.stat().st_size > maximum:
        raise PyChronoError(category, f"file exceeds {maximum} bytes: {path}")
    return path.read_bytes()


def _read_result_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise PyChronoError("result_missing", "child wrote no result.json")
    return _decode_json(
        _read_bounded(path, MAX_RESULT_BYTES, "result_malformed"),
        maximum=MAX_RESULT_BYTES,
        category="result_malformed",
    )


def _validate_manifest_identity(
    manifest: Mapping[str, object], request_id: str
) -> None:
    if (
        manifest.get("protocol") != PROTOCOL
        or manifest.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise PyChronoError("protocol_mismatch", "result protocol/version mismatch")
    if manifest.get("request_id") != request_id:
        raise PyChronoError("request_mismatch", "result request_id mismatch")


def _optional_error_manifest(
    result_path: Path, request_id: str
) -> dict[str, object] | None:
    try:
        manifest = _read_result_manifest(result_path)
        _validate_manifest_identity(manifest, request_id)
        return manifest
    except (PyChronoError, OSError):
        return None


def _validate_request_document(request: Mapping[str, object]) -> None:
    if (
        request.get("protocol") != PROTOCOL
        or request.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise PyChronoError("protocol_mismatch", "request protocol/version mismatch")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise PyChronoError("request_invalid", "request_id must be non-empty")
    parameters = request.get("parameters")
    if not isinstance(parameters, Mapping) or not isinstance(
        parameters.get("assigned"), Mapping
    ):
        raise PyChronoError(
            "request_invalid", "parameters.assigned must be an object"
        )
    _parameter_mapping(parameters["assigned"], normalized=False)  # type: ignore[arg-type]
    if "normalized" in parameters:
        normalized = parameters["normalized"]
        if not isinstance(normalized, Mapping):
            raise PyChronoError(
                "request_invalid", "parameters.normalized must be an object"
            )
        _parameter_mapping(normalized, normalized=True)
    context = request.get("context")
    if not isinstance(context, Mapping):
        raise PyChronoError("request_invalid", "context must be an object")
    if context.get("backend") not in {"fast", "local", "distributed"}:
        raise PyChronoError("request_invalid", "context backend is invalid")
    if not isinstance(context.get("evaluation_id"), str) or not str(
        context.get("evaluation_id")
    ).strip():
        raise PyChronoError("request_invalid", "context evaluation_id is invalid")
    if context.get("scratch_dir") != "." or context.get("rawdata_dir") != "rawData":
        raise PyChronoError("request_invalid", "context paths are invalid")
    if not isinstance(request.get("task_context", {}), Mapping):
        raise PyChronoError("request_invalid", "task_context must be an object")


def _resolved_worker(worker: str | Path) -> Path:
    path = Path(worker)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PyChronoError(
            "worker_missing", f"task child entry point is unavailable: {path}"
        ) from exc
    if not resolved.is_file():
        raise PyChronoError(
            "worker_missing", f"task child entry point is not a file: {resolved}"
        )
    return resolved


def _child_environment(
    overrides: Mapping[str, str] | None, *, scratch: Path | None = None
) -> dict[str, str]:
    output = {str(key): str(value) for key, value in os.environ.items()}
    if overrides:
        output.update({str(key): str(value) for key, value in overrides.items()})
    for key in tuple(output):
        if key.casefold() == "pythonpath":
            output.pop(key)
    output["PYTHONNOUSERSITE"] = "1"
    output["PYTHONDONTWRITEBYTECODE"] = "1"
    if scratch is not None:
        output["TEMP"] = str(scratch)
        output["TMP"] = str(scratch)
    return output


def _timeout_value(timeout: float | None) -> float | None:
    if timeout is None:
        return None
    if isinstance(timeout, bool):
        raise PyChronoError("request_invalid", "timeout must be a positive number")
    try:
        value = float(timeout)
    except (TypeError, ValueError) as exc:
        raise PyChronoError(
            "request_invalid", "timeout must be a positive number"
        ) from exc
    if not math.isfinite(value) or value <= 0.0:
        raise PyChronoError("request_invalid", "timeout must be a positive number")
    return value


def _scratch_root(root: str | Path, interpreter: Path) -> Path:
    selected = Path(root).resolve()
    try:
        selected.relative_to(_runtime_prefix(interpreter))
    except ValueError:
        pass
    else:
        raise PyChronoError(
            "request_invalid", "scratch_root must not be inside the runtime prefix"
        )
    try:
        selected.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PyChronoError(
            "request_invalid", f"could not create scratch_root {selected}: {exc}"
        ) from exc
    if not selected.is_dir():
        raise PyChronoError(
            "request_invalid", f"scratch_root is not a directory: {selected}"
        )
    return selected


def _runtime_prefix(interpreter: Path) -> Path:
    parent = interpreter.parent
    if parent.name.casefold() in {"bin", "scripts"}:
        return parent.parent
    return parent


def _wait_for_process(
    process: subprocess.Popen[bytes],
    *,
    timeout: float | None,
    cancel_requested: Callable[[], bool] | None,
) -> str | None:
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        if cancel_requested is not None:
            try:
                if bool(cancel_requested()):
                    return "cancelled"
            except Exception as exc:
                raise PyChronoError(
                    "cancelled", f"cancellation callback failed: {exc}"
                ) from exc
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0.0:
            return "timeout"
        interval = _POLL_INTERVAL_SEC if remaining is None else min(_POLL_INTERVAL_SEC, remaining)
        try:
            process.wait(timeout=interval)
            return None
        except subprocess.TimeoutExpired:
            continue


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        tracked: list[object] = []
        try:
            import psutil

            root = psutil.Process(process.pid)
            tracked = [*root.children(recursive=True), root]
        except (ImportError, OSError):
            psutil = None  # type: ignore[assignment]
        except Exception:
            psutil = None  # type: ignore[assignment]
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if psutil is not None:
            for tracked_process in reversed(tracked):
                try:
                    tracked_process.kill()  # type: ignore[attr-defined]
                except (psutil.Error, OSError):
                    pass
            if tracked:
                psutil.wait_procs(tracked, timeout=_TERMINATION_WAIT_SEC)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _file_tail(path: Path) -> tuple[str, bool]:
    if not path.is_file():
        return "", False
    size = path.stat().st_size
    with path.open("rb") as stream:
        if size > MAX_DIAGNOSTIC_BYTES:
            stream.seek(-MAX_DIAGNOSTIC_BYTES, os.SEEK_END)
        payload = stream.read(MAX_DIAGNOSTIC_BYTES)
    return payload.decode("utf-8", errors="replace"), size > MAX_DIAGNOSTIC_BYTES


def _is_reparse_point(path: Path) -> bool:
    try:
        information = path.lstat()
    except OSError:
        return True
    attributes = int(getattr(information, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return path.is_symlink() or bool(reparse_flag and attributes & reparse_flag)


def _validated_manifest_rawdata(
    scratch: Path, manifest: Mapping[str, object]
) -> tuple[tuple[Path, ...], dict[str, Mapping[str, object]]]:
    raw_entries = manifest.get("rawdata")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise PyChronoError("rawdata_missing", "success listed no rawData")
    raw_dir = scratch / "rawData"
    if not raw_dir.is_dir() or _is_reparse_point(raw_dir):
        raise PyChronoError("rawdata_missing", "child rawData directory is missing")

    expected: dict[str, Mapping[str, object]] = {}
    paths: list[Path] = []
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            raise PyChronoError(
                "result_malformed", "rawdata entries must be objects"
            )
        relative_text = entry.get("path")
        if not isinstance(relative_text, str) or "\\" in relative_text:
            raise PyChronoError("output_path_invalid", "rawData path is invalid")
        relative = PurePosixPath(relative_text)
        if (
            relative.is_absolute()
            or relative.parts != ("rawData", relative.name)
            or relative.name in {"", ".", ".."}
            or relative.suffix.casefold() != ".npz"
        ):
            raise PyChronoError("output_path_invalid", relative_text)
        folded = relative.name.casefold()
        if folded in expected:
            raise PyChronoError(
                "output_path_invalid", "rawData names must be unique ignoring case"
            )
        candidate = raw_dir / relative.name
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise PyChronoError("rawdata_missing", relative_text) from exc
        if (
            resolved.parent != raw_dir.resolve()
            or not resolved.is_file()
            or _is_reparse_point(candidate)
        ):
            raise PyChronoError("output_path_invalid", relative_text)
        size = entry.get("size_bytes")
        digest = entry.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise PyChronoError(
                "result_malformed", "rawData size_bytes must be non-negative integer"
            )
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise PyChronoError(
                "result_malformed", "rawData sha256 must be lowercase hexadecimal"
            )
        if resolved.stat().st_size != size or _sha256(resolved) != digest:
            raise PyChronoError("rawdata_invalid", f"rawData digest mismatch: {relative.name}")
        expected[folded] = entry
        paths.append(resolved)

    actual = tuple(raw_dir.iterdir())
    if any(not path.is_file() or _is_reparse_point(path) for path in actual):
        raise PyChronoError("rawdata_invalid", "child rawData directory must be flat")
    if {path.name.casefold() for path in actual} != set(expected):
        raise PyChronoError("rawdata_invalid", "child rawData contains unlisted files")
    payloads = {path.name: _validate_npz(path) for path in paths}
    return tuple(paths), payloads


def _validated_rawdata_directory(
    rawdata_dir: Path,
) -> tuple[tuple[Path, ...], dict[str, Mapping[str, object]]]:
    if not rawdata_dir.is_dir() or _is_reparse_point(rawdata_dir):
        raise PyChronoError("rawdata_missing", "child wrote no rawData directory")
    entries = tuple(rawdata_dir.iterdir())
    if not entries:
        raise PyChronoError("rawdata_missing", "child wrote no rawData files")
    seen: set[str] = set()
    paths: list[Path] = []
    payloads: dict[str, Mapping[str, object]] = {}
    for path in sorted(entries, key=lambda item: item.name.casefold()):
        if (
            not path.is_file()
            or _is_reparse_point(path)
            or path.suffix.casefold() != ".npz"
            or path.name.casefold() in seen
        ):
            raise PyChronoError(
                "rawdata_invalid", "child rawData must contain unique direct NPZ files"
            )
        seen.add(path.name.casefold())
        paths.append(path)
        payloads[path.name] = _validate_npz(path)
    return tuple(paths), payloads


def _validate_npz(path: Path) -> dict[str, object]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            payload = {key: archive[key].copy() for key in archive.files}
    except Exception as exc:
        raise PyChronoError("rawdata_invalid", f"invalid NPZ {path.name}: {exc}") from exc
    if "metadata" not in payload:
        raise PyChronoError("rawdata_invalid", f"{path.name} has no metadata")
    metadata_array = np.asarray(payload["metadata"])
    if metadata_array.shape != ():
        raise PyChronoError("rawdata_invalid", f"{path.name} metadata must be scalar")
    metadata_value = metadata_array.item()
    if isinstance(metadata_value, bytes):
        try:
            metadata_value = metadata_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PyChronoError(
                "rawdata_invalid", f"{path.name} metadata is not UTF-8"
            ) from exc
    if not isinstance(metadata_value, str):
        raise PyChronoError("rawdata_invalid", f"{path.name} metadata must be JSON text")
    metadata = _decode_json(
        metadata_value.encode("utf-8"),
        maximum=MAX_RESULT_BYTES,
        category="rawdata_invalid",
    )
    if metadata.get("schema_version") != RAWDATA_SCHEMA_VERSION:
        raise PyChronoError("rawdata_invalid", f"{path.name} schema_version must be 1")
    data_key = "values" if "values" in payload else "data" if "data" in payload else None
    if data_key is None:
        raise PyChronoError("rawdata_invalid", f"{path.name} has no values/data array")
    data = np.asarray(payload[data_key])
    _finite_real_array(data, f"{path.name}:{data_key}")
    shape = metadata.get("shape")
    if not isinstance(shape, list) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in shape
    ):
        raise PyChronoError("rawdata_invalid", f"{path.name} metadata shape is invalid")
    expected_shape = tuple(shape)
    if data.shape != expected_shape:
        raise PyChronoError(
            "rawdata_invalid",
            f"{path.name} shape mismatch: metadata {expected_shape}, data {data.shape}",
        )
    axes = metadata.get("axes")
    if axes is not None:
        if not isinstance(axes, list) or len(axes) != len(expected_shape):
            raise PyChronoError("rawdata_invalid", f"{path.name} metadata axes are invalid")
        for index, descriptor in enumerate(axes):
            if not isinstance(descriptor, Mapping):
                raise PyChronoError("rawdata_invalid", f"{path.name} axis is not an object")
            if descriptor.get("index") != index or descriptor.get("size") != expected_shape[index]:
                raise PyChronoError("rawdata_invalid", f"{path.name} axis descriptor mismatch")
            values_key = descriptor.get("values_key")
            if values_key is not None:
                if not isinstance(values_key, str) or values_key not in payload:
                    raise PyChronoError("rawdata_invalid", f"{path.name} axis values are missing")
                axis_values = np.asarray(payload[values_key])
                _finite_real_array(axis_values, f"{path.name}:{values_key}")
                if axis_values.ndim == 0 or axis_values.shape[0] != expected_shape[index]:
                    raise PyChronoError("rawdata_invalid", f"{path.name} axis size mismatch")
    for key, value in payload.items():
        array = np.asarray(value)
        if array.dtype.hasobject or array.dtype.fields is not None:
            raise PyChronoError("rawdata_invalid", f"{path.name}:{key} has forbidden dtype")
    return payload


def _finite_real_array(array: np.ndarray, label: str) -> None:
    if array.dtype.kind not in "biuf" or not np.all(np.isfinite(array)):
        raise PyChronoError("rawdata_invalid", f"{label} must be finite real numeric data")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_rawdata(
    source_paths: Sequence[Path],
    destination: str | Path,
    *,
    forbidden_root: Path,
    runtime_prefix: Path,
) -> tuple[Path, ...]:
    selected = Path(destination).resolve()
    for forbidden, label in (
        (forbidden_root, "child scratch"),
        (runtime_prefix, "external runtime prefix"),
    ):
        try:
            selected.relative_to(forbidden)
        except ValueError:
            continue
        raise PyChronoError(
            "output_path_invalid", f"final rawdata_dir must be outside {label}"
        )
    try:
        selected.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PyChronoError(
            "rawdata_invalid", f"could not create final rawdata_dir: {exc}"
        ) from exc
    existing = {path.name.casefold() for path in selected.iterdir()}
    collisions = [path.name for path in source_paths if path.name.casefold() in existing]
    if collisions:
        raise PyChronoError(
            "rawdata_invalid", f"final rawData names already exist: {', '.join(collisions)}"
        )
    temporary: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for source in source_paths:
            final = selected / source.name
            partial = selected / f".{source.name}.{uuid.uuid4().hex}.part"
            shutil.copyfile(source, partial)
            temporary.append((partial, final))
        for partial, final in temporary:
            os.replace(partial, final)
            published.append(final)
    except OSError as exc:
        for path in published:
            path.unlink(missing_ok=True)
        raise PyChronoError(
            "rawdata_invalid", f"could not publish final rawData: {exc}"
        ) from exc
    finally:
        for partial, _final in temporary:
            partial.unlink(missing_ok=True)
    return tuple(published)


def _remove_scratch(scratch: Path) -> str | None:
    try:
        shutil.rmtree(scratch)
    except OSError as exc:
        return str(exc)
    return None


def _validate_worker_paths(request_path: Path, result_path: Path) -> None:
    cwd = Path.cwd().resolve()
    if not request_path.is_absolute() or not result_path.is_absolute():
        raise PyChronoError("request_invalid", "request/result paths must be absolute")
    if request_path.resolve().parent != cwd or result_path.resolve().parent != cwd:
        raise PyChronoError(
            "request_invalid", "request/result paths must be direct child-scratch files"
        )
    if request_path.name != "request.json" or result_path.name != "result.json":
        raise PyChronoError("request_invalid", "request/result filenames are invalid")


def _write_worker_error(
    result_path: Path, request_id: str, code: str, message: str
) -> None:
    bounded = str(message).replace("\x00", "")[-4000:]
    manifest: dict[str, object] = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": "error",
        "rawdata": [],
        "error": {"code": code, "message": bounded or code},
        "diagnostics": {},
    }
    try:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(result_path, manifest, maximum=MAX_RESULT_BYTES)
    except Exception:
        traceback.print_exc()


__all__ = [
    "MAX_DIAGNOSTIC_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROTOCOL",
    "PROTOCOL_VERSION",
    "PyChronoError",
    "PyChronoResult",
    "build_request",
    "resolve_interpreter",
    "run_pychrono",
    "worker_main",
]
