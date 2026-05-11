from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from . import paths

RawDataItem = dict[str, object] | Path


def metadata_from_npz(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as data:
        if "metadata" not in data.files:
            return {}
        raw = data["metadata"].item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_npz(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def rawdata_paths_for_record(record: Mapping[str, object]) -> tuple[Path, ...]:
    job_name = str(record["job_name"])
    filenames = tuple(str(name) for name in record.get("rawdata_files", ()))
    return tuple(paths.RAWDATA_ROOT / job_name / filename for filename in filenames)


def source_files(rawdata_source: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(rawdata_source, (str, Path)):
        source_path = Path(rawdata_source)
        if source_path.is_dir():
            subdirs = [path for path in source_path.iterdir() if path.is_dir()]
            if subdirs:
                names = ", ".join(path.name for path in sorted(subdirs, key=lambda p: p.name.lower()))
                raise ValueError(f"rawData directory must be flat; found subdirectories: {names}")
            return sorted(
                path for path in source_path.iterdir() if path.is_file() and path.suffix.lower() == ".npz"
            )
        return [source_path]
    return [Path(path) for path in rawdata_source]
