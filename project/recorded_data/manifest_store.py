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
from .utils import json_ready

_PROCESS_LOCK = threading.RLock()
_LOCK_STATE = threading.local()


def metadata_lock_path() -> Path:
    return paths.IND_META_PATH.with_suffix(paths.IND_META_PATH.suffix + ".lock")


@contextmanager
def metadata_lock():
    with _PROCESS_LOCK:
        depth = int(getattr(_LOCK_STATE, "depth", 0))
        if depth:
            _LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LOCK_STATE.depth = depth
            return

        lock_path = metadata_lock_path()
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
                    raise TimeoutError(f"timed out waiting for recorded_data lock: {metadata_lock_path()}")
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


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(loaded, dict):
                raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
            records.append(loaded)
    return records


def read_individual_records() -> list[dict[str, object]]:
    return read_jsonl(paths.IND_META_PATH)


def read_optimization_metadata() -> list[dict[str, object]]:
    return read_jsonl(paths.OPT_META_PATH)


def append_jsonl_unlocked(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(json_ready(dict(data)), ensure_ascii=False, sort_keys=True) + "\n")


def append_individual_record_unlocked(record: Mapping[str, object]) -> None:
    append_jsonl_unlocked(paths.IND_META_PATH, record)


def append_optimization_metadata_unlocked(record: Mapping[str, object]) -> None:
    append_jsonl_unlocked(paths.OPT_META_PATH, record)


def write_individual_records_unlocked(records: Iterable[Mapping[str, object]]) -> None:
    _write_jsonl_unlocked(paths.IND_META_PATH, records)


def _write_jsonl_unlocked(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(json_ready(dict(record)), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write(text)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


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
