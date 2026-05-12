from __future__ import annotations

import ctypes
import os
import shutil
import stat
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = PROJECT_ROOT / "jobs"
SURROGATE_CHECKPOINTS_DIR = PROJECT_ROOT / "surrogate" / "checkpoints"
RECORDED_RAWDATA_DIR = PROJECT_ROOT / "recorded_data" / "rawData"
RECORDED_MANIFEST_PATH = PROJECT_ROOT / "recorded_data" / "manifest.json"


def _is_under_project(path: Path) -> bool:
    project_root = PROJECT_ROOT.resolve()
    resolved = path.resolve(strict=False)
    return resolved == project_root or resolved.is_relative_to(project_root)


def _require_project_path(path: Path) -> None:
    if not _is_under_project(path):
        raise RuntimeError(f"refusing to operate outside project root: {path}")


def _make_writable_and_retry(func, path_text: str, _exc_info) -> None:
    path = Path(path_text)
    try:
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except OSError:
        pass
    func(path_text)


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker()) if callable(checker) else False


def _permanently_delete(path: Path) -> None:
    _require_project_path(path)
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink() and not _is_junction(path):
        shutil.rmtree(path, onerror=_make_writable_and_retry)
        return
    try:
        path.unlink()
    except IsADirectoryError:
        path.rmdir()


def _empty_directory_permanently(directory: Path) -> int:
    _require_project_path(directory)
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=True)
        return 0
    if not directory.is_dir():
        raise RuntimeError(f"expected a directory: {directory}")

    count = 0
    for child in tuple(directory.iterdir()):
        _permanently_delete(child)
        count += 1
    return count


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = (
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    )


def _move_to_recycle_bin_windows(path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Recycle Bin cleanup is only implemented for Windows")

    shell32 = ctypes.windll.shell32
    operation = _SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = 0x0003  # FO_DELETE
    operation.pFrom = str(path.resolve()) + "\0\0"
    operation.pTo = None
    operation.fFlags = 0x0040 | 0x0010 | 0x0400 | 0x0004
    operation.fAnyOperationsAborted = 0
    operation.hNameMappings = None
    operation.lpszProgressTitle = None

    result = shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(result, f"failed to move to Recycle Bin: {path}")
    if operation.fAnyOperationsAborted:
        raise RuntimeError(f"Recycle Bin operation was aborted: {path}")


def _move_to_recycle_bin(path: Path) -> bool:
    _require_project_path(path)
    if not path.exists():
        return False
    _move_to_recycle_bin_windows(path)
    return True


def clear_history() -> dict[str, object]:
    jobs_deleted = _empty_directory_permanently(JOBS_DIR)
    checkpoints_existed = SURROGATE_CHECKPOINTS_DIR.exists()
    _permanently_delete(SURROGATE_CHECKPOINTS_DIR)
    rawdata_recycled = _move_to_recycle_bin(RECORDED_RAWDATA_DIR)
    manifest_recycled = _move_to_recycle_bin(RECORDED_MANIFEST_PATH)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    return {
        "project_root": str(PROJECT_ROOT),
        "jobs_entries_permanently_deleted": jobs_deleted,
        "surrogate_checkpoints_permanently_deleted": checkpoints_existed,
        "recorded_rawdata_moved_to_recycle_bin": rawdata_recycled,
        "recorded_manifest_moved_to_recycle_bin": manifest_recycled,
    }


def main() -> int:
    summary = clear_history()
    print("Historical optimization results cleared.")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
