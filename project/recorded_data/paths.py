from __future__ import annotations

from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = MODULE_DIR / "manifest.json"
RAWDATA_ROOT = MODULE_DIR / "rawData"

MANIFEST_SCHEMA_VERSION = 1
VALID_RECORD_STATUSES = ("completed", "error", "timeout")


def configure(
    *,
    module_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    rawdata_root: str | Path | None = None,
) -> None:
    global MODULE_DIR, MANIFEST_PATH, RAWDATA_ROOT

    if module_dir is not None:
        MODULE_DIR = Path(module_dir)
    if manifest_path is not None:
        MANIFEST_PATH = Path(manifest_path)
    else:
        MANIFEST_PATH = MODULE_DIR / "manifest.json"
    if rawdata_root is not None:
        RAWDATA_ROOT = Path(rawdata_root)
    else:
        RAWDATA_ROOT = MODULE_DIR / "rawData"
