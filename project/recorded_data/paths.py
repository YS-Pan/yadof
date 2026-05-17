from __future__ import annotations

from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
IND_META_PATH = MODULE_DIR / "indMeta.jsonl"
RAWDATA_ARCHIVE_PATH = MODULE_DIR / "rawData.npz"
OPT_META_DIR = MODULE_DIR / "optMeta"
OPT_META_PATH = OPT_META_DIR / "optMeta.jsonl"

IND_META_SCHEMA_VERSION = 1
OPT_META_SCHEMA_VERSION = 1
VALID_RECORD_STATUSES = ("completed", "error", "timeout")


def configure(
    *,
    module_dir: str | Path | None = None,
    ind_meta_path: str | Path | None = None,
    rawdata_archive_path: str | Path | None = None,
    opt_meta_dir: str | Path | None = None,
    opt_meta_path: str | Path | None = None,
) -> None:
    global MODULE_DIR, IND_META_PATH, RAWDATA_ARCHIVE_PATH, OPT_META_DIR, OPT_META_PATH

    if module_dir is not None:
        MODULE_DIR = Path(module_dir)
    if ind_meta_path is not None:
        IND_META_PATH = Path(ind_meta_path)
    else:
        IND_META_PATH = MODULE_DIR / "indMeta.jsonl"
    if rawdata_archive_path is not None:
        RAWDATA_ARCHIVE_PATH = Path(rawdata_archive_path)
    else:
        RAWDATA_ARCHIVE_PATH = MODULE_DIR / "rawData.npz"
    if opt_meta_dir is not None:
        OPT_META_DIR = Path(opt_meta_dir)
    else:
        OPT_META_DIR = MODULE_DIR / "optMeta"
    if opt_meta_path is not None:
        OPT_META_PATH = Path(opt_meta_path)
    else:
        OPT_META_PATH = OPT_META_DIR / "optMeta.jsonl"
