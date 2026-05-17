from __future__ import annotations

from io import BytesIO
import json
import shutil
from pathlib import Path
from typing import Mapping, Sequence
import zipfile

import numpy as np

from . import paths

RawDataItem = dict[str, object] | str
RAWDATA_METADATA_FORBIDDEN_KEYS = {
    "variables",
    "raw_variables",
    "unnormalized_variables",
    "normalized_variables",
    "job_metadata",
}


def metadata_from_npz(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as data:
        return _metadata_from_npz_payload(data)


def _metadata_from_npz_payload(data) -> dict[str, object]:
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
    return _scrub_rawdata_metadata(loaded) if isinstance(loaded, dict) else {}


def _scrub_rawdata_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _scrub_rawdata_metadata(item)
            for key, item in value.items()
            if str(key) not in RAWDATA_METADATA_FORBIDDEN_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_rawdata_metadata(item) for item in value]
    return value


def load_npz(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def load_archive_member(member_name: str) -> dict[str, object]:
    with zipfile.ZipFile(paths.RAWDATA_ARCHIVE_PATH, "r") as archive:
        return load_archive_member_from_archive(archive, member_name)


def load_archive_member_from_archive(archive: zipfile.ZipFile, member_name: str) -> dict[str, object]:
    with archive.open(member_name, "r") as member_file:
        payload = member_file.read()
    with np.load(BytesIO(payload), allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def load_archive_members_from_archive(
    archive: zipfile.ZipFile,
    member_names: Sequence[str],
) -> tuple[dict[str, object], ...]:
    return tuple(load_archive_member_from_archive(archive, member_name) for member_name in member_names)


def rawdata_members_for_record(record: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(str(name) for name in record.get("rawdata_files", ()))


def rawdata_items_for_record(record: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(load_archive_member(member) for member in rawdata_members_for_record(record))


def rawdata_member_name(job_name: str, filename: str) -> str:
    clean_filename = Path(filename).name
    return f"{job_name}/{clean_filename}"


def append_rawdata_files(job_name: str, source_paths: Sequence[Path]) -> tuple[list[str], dict[str, object]]:
    if not source_paths:
        return [], {}

    paths.RAWDATA_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    members: list[str] = []
    metadata: dict[str, object] = {}
    archive_path = paths.RAWDATA_ARCHIVE_PATH
    temp_path = archive_path.with_name(f"{archive_path.name}.tmp")
    try:
        if archive_path.exists():
            shutil.copy2(archive_path, temp_path)
            mode = "a"
        else:
            mode = "w"
        with zipfile.ZipFile(temp_path, mode, compression=zipfile.ZIP_STORED, allowZip64=True) as target:
            existing = set(target.namelist())
            for source_file in source_paths:
                member = rawdata_member_name(job_name, source_file.name)
                if member in existing:
                    raise ValueError(f"rawData archive already contains member {member!r}")
                target.write(source_file, member)
                existing.add(member)
                members.append(member)
                metadata[member] = metadata_from_npz(source_file)
        temp_path.replace(archive_path)
        return members, metadata
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def remove_archive_members_for_job(job_name: str) -> None:
    archive_path = paths.RAWDATA_ARCHIVE_PATH
    if not archive_path.exists():
        return

    prefix = f"{job_name}/"
    temp_path = archive_path.with_name(f"{archive_path.name}.tmp")
    try:
        with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(
            temp_path,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as target:
            for info in source.infolist():
                if info.filename.startswith(prefix):
                    continue
                target.writestr(info, source.read(info.filename))
        temp_path.replace(archive_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


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
