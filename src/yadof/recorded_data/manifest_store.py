"""Locked and atomic JSONL persistence for workspace recorded data."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterable, Mapping

from .paths import RecordedDataPaths, VALID_RECORD_STATUSES


_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()
_LOCK_STATE = threading.local()


def _process_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def metadata_lock(storage: RecordedDataPaths):
    """Serialize metadata and archive access within and across processes."""

    with _metadata_lock(storage, create=True):
        yield


@contextmanager
def metadata_read_lock(storage: RecordedDataPaths):
    """Join an existing file lock without creating state for an empty history."""

    with _metadata_lock(storage, create=False):
        yield


@contextmanager
def _metadata_lock(storage: RecordedDataPaths, *, create: bool):
    """Acquire the process lock and, when present or requested, the file lock."""

    lock_path = storage.lock_path
    key = os.path.normcase(str(lock_path.resolve()))
    with _process_lock(lock_path):
        held = set(getattr(_LOCK_STATE, "held", set()))
        if key in held:
            yield
            return

        if create:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        elif not lock_path.is_file():
            yield
            return
        flags = os.O_RDWR | os.O_CREAT if create else os.O_RDWR
        try:
            fd = os.open(lock_path, flags)
        except FileNotFoundError:
            yield
            return
        with os.fdopen(fd, "r+b") as lock_file:
            _acquire_file_lock(lock_file, lock_path)
            _LOCK_STATE.held = held | {key}
            try:
                yield
            finally:
                _LOCK_STATE.held = held
                _release_file_lock(lock_file)


def _acquire_file_lock(lock_file, lock_path: Path) -> None:
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
                    raise TimeoutError(
                        f"timed out waiting for recorded_data lock: {lock_path}"
                    )
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


def read_individual_records(storage: RecordedDataPaths) -> list[dict[str, object]]:
    return read_jsonl(storage.ind_meta_path)


def read_optimization_metadata(storage: RecordedDataPaths) -> list[dict[str, object]]:
    return read_jsonl(storage.opt_meta_path)


def append_jsonl_unlocked(path: Path, data: Mapping[str, object]) -> None:
    records = read_jsonl(path)
    records.append(dict(data))
    _write_jsonl_unlocked(path, records)


def append_individual_record_unlocked(
    storage: RecordedDataPaths, record: Mapping[str, object]
) -> None:
    append_jsonl_unlocked(storage.ind_meta_path, record)


def append_optimization_metadata_unlocked(
    storage: RecordedDataPaths, record: Mapping[str, object]
) -> None:
    append_jsonl_unlocked(storage.opt_meta_path, record)


def write_individual_records_unlocked(
    storage: RecordedDataPaths, records: Iterable[Mapping[str, object]]
) -> None:
    _write_jsonl_unlocked(storage.ind_meta_path, records)


def _write_jsonl_unlocked(
    path: Path, records: Iterable[Mapping[str, object]]
) -> None:
    from .utils import json_ready

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
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def find_record(
    records: Iterable[Mapping[str, object]], job_name: str
) -> Mapping[str, object] | None:
    for record in records:
        if str(record.get("job_name")) == job_name:
            return record
    return None


def canonical_status(status: str) -> str:
    clean_status = str(status).strip().lower()
    if clean_status == "done":
        clean_status = "completed"
    if clean_status not in VALID_RECORD_STATUSES:
        raise ValueError(
            f"status must be one of {VALID_RECORD_STATUSES!r}, got {status!r}"
        )
    return clean_status
