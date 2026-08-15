"""Non-stale OS-backed exclusivity for one workspace campaign."""

from __future__ import annotations

import os
from pathlib import Path
import threading


class CampaignActiveError(RuntimeError):
    """Raised when a workspace already has an active optimization campaign."""


_HELD_PATHS: set[str] = set()
_HELD_GUARD = threading.Lock()


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


class CampaignLock:
    """Own one non-blocking process/file lock until explicitly released."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._file = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> None:
        key = _key(self.path)
        with _HELD_GUARD:
            if key in _HELD_PATHS:
                raise CampaignActiveError(_message(self.path))
            _HELD_PATHS.add(key)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = self.path.open("a+b")
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            with _HELD_GUARD:
                _HELD_PATHS.discard(key)
            try:
                lock_file.close()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            raise CampaignActiveError(_message(self.path)) from exc
        self._file = lock_file
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        lock_file = self._file
        self._file = None
        self._held = False
        try:
            if lock_file is not None:
                if os.name == "nt":
                    import msvcrt

                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
        finally:
            with _HELD_GUARD:
                _HELD_PATHS.discard(_key(self.path))


def assert_campaign_inactive(path: Path) -> None:
    """Fail fast when a destructive operation targets an active workspace."""

    lock = CampaignLock(path)
    lock.acquire()
    lock.release()


def _message(path: Path) -> str:
    return (
        f"workspace campaign is already active ({path}); use another workspace "
        "for a concurrent optimization and retry destructive history operations "
        "after the active campaign exits"
    )


__all__ = ["CampaignActiveError", "CampaignLock", "assert_campaign_inactive"]
