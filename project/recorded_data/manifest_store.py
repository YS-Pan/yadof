from __future__ import annotations

from contextlib import contextmanager
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterable, Mapping

from . import paths
from .utils import json_ready, now_utc_text

_PROCESS_LOCK = threading.RLock()
_LOCK_STATE = threading.local()


def manifest_lock_path() -> Path:
    return paths.MANIFEST_PATH.with_suffix(paths.MANIFEST_PATH.suffix + ".lock")


@contextmanager
def manifest_lock():
    with _PROCESS_LOCK:
        depth = int(getattr(_LOCK_STATE, "depth", 0))
        if depth:
            _LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LOCK_STATE.depth = depth
            return

        lock_path = manifest_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
        with os.fdopen(fd, "r+b") as lock_file:
            _acquire_file_lock(lock_file)
            _LOCK_STATE.depth = 1
            try:
                yield
            finally:
                _LOCK_STATE.depth = 0
                _release_file_lock(lock_file)


def _acquire_file_lock(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        deadline = time.monotonic() + 60.0
        while True:
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for manifest lock: {manifest_lock_path()}")
                time.sleep(0.02)

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _release_file_lock(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def manifest_with_metadata(manifest: Mapping[str, object], *, updated_at: str | None = None) -> dict[str, object]:
    normalized = dict(manifest)
    normalized["schema_version"] = paths.MANIFEST_SCHEMA_VERSION
    normalized["record_statuses"] = list(paths.VALID_RECORD_STATUSES)
    normalized["updated_at"] = updated_at
    normalized.setdefault("records", [])
    record_list(normalized)
    return normalized


def read_manifest() -> dict[str, object]:
    if not paths.MANIFEST_PATH.exists():
        return manifest_with_metadata({"records": []})
    try:
        loaded = json.loads(paths.MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest is not valid JSON: {paths.MANIFEST_PATH}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"manifest must be a JSON object: {paths.MANIFEST_PATH}")
    updated_at = loaded.get("updated_at")
    return manifest_with_metadata(loaded, updated_at=updated_at if isinstance(updated_at, str) else None)


def write_manifest(manifest: Mapping[str, object]) -> None:
    with manifest_lock():
        write_manifest_unlocked(manifest)


def write_manifest_unlocked(manifest: Mapping[str, object]) -> None:
    paths.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest_to_write = manifest_with_metadata(manifest, updated_at=now_utc_text())
    text = json.dumps(json_ready(manifest_to_write), indent=2, ensure_ascii=False)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{paths.MANIFEST_PATH.name}.",
        suffix=".tmp",
        dir=str(paths.MANIFEST_PATH.parent),
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write(text)
        temp_path.replace(paths.MANIFEST_PATH)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def record_list(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    records = manifest.get("records", [])
    if not isinstance(records, list):
        raise ValueError("manifest field 'records' must be a list")
    return records  # type: ignore[return-value]


def find_record(records: Iterable[Mapping[str, object]], job_name: str) -> Mapping[str, object] | None:
    for record in records:
        if str(record.get("job_name")) == job_name:
            return record
    return None


def canonical_status(status: str) -> str:
    clean_status = str(status).strip().lower()
    if clean_status == "done":
        clean_status = "completed"
    if clean_status not in paths.VALID_RECORD_STATUSES:
        raise ValueError(f"status must be one of {paths.VALID_RECORD_STATUSES!r}, got {status!r}")
    return clean_status
