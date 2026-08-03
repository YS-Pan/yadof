"""Zip-based rawData persistence below an explicit workspace path."""

from __future__ import annotations

from io import BytesIO
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping, Sequence
import zipfile

import numpy as np

from ..job_template.rawdata_contract import (
    NamedRawDataItem,
    metadata_from_item,
    validate_rawdata_item,
)
from .paths import RecordedDataPaths


RawDataItem = dict[str, object] | str
RawDataSourceItem = Path | NamedRawDataItem
RawDataSource = (
    str
    | Path
    | NamedRawDataItem
    | Sequence[str | Path | NamedRawDataItem]
)
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


def _metadata_from_memory_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return _scrub_rawdata_metadata(metadata_from_item(payload))


def _npz_bytes_from_memory_item(item: NamedRawDataItem) -> bytes:
    validated = validate_rawdata_item(item.payload)
    arrays: dict[str, np.ndarray] = {}
    for key, value in validated.items():
        if key == "metadata":
            arrays[key] = np.asarray(
                json.dumps(metadata_from_item(validated), ensure_ascii=True, sort_keys=True)
            )
            continue
        array = np.asarray(value)
        if array.dtype.hasobject:
            raise ValueError(
                f"in-memory rawData {item.filename!r} field {key!r} "
                "would require pickle"
            )
        arrays[str(key)] = array
    buffer = BytesIO()
    np.savez_compressed(buffer, **arrays)
    payload = buffer.getvalue()
    with np.load(BytesIO(payload), allow_pickle=False) as loaded:
        validate_rawdata_item({key: loaded[key].copy() for key in loaded.files})
    return payload


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


def load_archive_member(
    storage: RecordedDataPaths, member_name: str
) -> dict[str, object]:
    with zipfile.ZipFile(storage.rawdata_archive_path, "r") as archive:
        return load_archive_member_from_archive(archive, member_name)


def load_archive_member_from_archive(
    archive: zipfile.ZipFile, member_name: str
) -> dict[str, object]:
    with archive.open(member_name, "r") as member_file:
        payload = member_file.read()
    with np.load(BytesIO(payload), allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def load_archive_members_from_archive(
    archive: zipfile.ZipFile,
    member_names: Sequence[str],
) -> tuple[dict[str, object], ...]:
    return tuple(
        load_archive_member_from_archive(archive, member_name)
        for member_name in member_names
    )


def rawdata_members_for_record(record: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(str(name) for name in record.get("rawdata_files", ()))


def rawdata_member_name(job_name: str, filename: str) -> str:
    clean_filename = Path(filename).name
    return f"{job_name}/{clean_filename}"


def write_rawdata_files(
    storage: RecordedDataPaths,
    job_name: str,
    source_paths: Sequence[RawDataSourceItem],
) -> tuple[list[str], dict[str, object]]:
    """Atomically replace one job's archive members and recover orphan members."""

    return write_rawdata_file_groups(storage, ((job_name, source_paths),))[job_name]


def write_rawdata_file_groups(
    storage: RecordedDataPaths,
    groups: Sequence[tuple[str, Sequence[RawDataSourceItem]]],
) -> dict[str, tuple[list[str], dict[str, object]]]:
    """Atomically replace several jobs while copying the archive at most once."""

    clean_groups: list[tuple[str, tuple[RawDataSourceItem, ...]]] = []
    seen_jobs: set[str] = set()
    prepared_items: dict[
        str,
        list[tuple[RawDataSourceItem, str, dict[str, object], bytes | None]],
    ] = {}
    outputs: dict[str, tuple[list[str], dict[str, object]]] = {}
    for job_name, source_paths in groups:
        clean_job_name = str(job_name)
        if clean_job_name in seen_jobs:
            raise ValueError(f"duplicate rawData job group: {clean_job_name!r}")
        seen_jobs.add(clean_job_name)
        sources = tuple(source_paths)
        clean_groups.append((clean_job_name, sources))
        outputs[clean_job_name] = ([], {})
        items: list[
            tuple[RawDataSourceItem, str, dict[str, object], bytes | None]
        ] = []
        seen_members: set[str] = set()
        for source in sources:
            filename = (
                source.filename
                if isinstance(source, NamedRawDataItem)
                else source.name
            )
            member = rawdata_member_name(clean_job_name, filename)
            folded_member = member.casefold()
            if folded_member in seen_members:
                raise ValueError(f"duplicate rawData archive member {member!r}")
            seen_members.add(folded_member)
            if isinstance(source, NamedRawDataItem):
                item_bytes = _npz_bytes_from_memory_item(source)
                item_metadata = _metadata_from_memory_payload(source.payload)
            else:
                item_bytes = None
                item_metadata = metadata_from_npz(source)
            items.append((source, member, item_metadata, item_bytes))
        prepared_items[clean_job_name] = items

    if not clean_groups:
        return outputs

    archive_path = storage.rawdata_archive_path
    existing_members: tuple[str, ...] = ()
    if archive_path.exists():
        with zipfile.ZipFile(archive_path, "r") as archive:
            existing_members = tuple(archive.namelist())
    prefixes = tuple(f"{job_name}/" for job_name, _paths in clean_groups)
    has_replaced_members = any(
        name.startswith(prefix)
        for name in existing_members
        for prefix in prefixes
    )

    if not any(paths for _job_name, paths in clean_groups) and not has_replaced_members:
        return outputs

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{archive_path.name}.",
        suffix=".tmp",
        dir=str(archive_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        if archive_path.exists() and not has_replaced_members:
            shutil.copy2(archive_path, temp_path)
            mode = "a"
        else:
            temp_path.unlink(missing_ok=True)
            mode = "w"
            if archive_path.exists():
                with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(
                    temp_path,
                    "w",
                    compression=zipfile.ZIP_STORED,
                    allowZip64=True,
                ) as target:
                    for info in source.infolist():
                        if not any(
                            info.filename.startswith(prefix) for prefix in prefixes
                        ):
                            target.writestr(info, source.read(info.filename))
                mode = "a"

        with zipfile.ZipFile(
            temp_path,
            mode,
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as target:
            names = set(target.namelist())
            for job_name, _source_paths in clean_groups:
                members, metadata = outputs[job_name]
                for source, member, item_metadata, item_bytes in prepared_items[job_name]:
                    if member in names:
                        raise ValueError(
                            f"rawData archive already contains member {member!r}"
                        )
                    if item_bytes is None:
                        target.write(source, member)
                    else:
                        target.writestr(member, item_bytes)
                    names.add(member)
                    members.append(member)
                    metadata[member] = item_metadata

        os.replace(temp_path, archive_path)
        return outputs
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def source_files(
    rawdata_source: str | Path | Sequence[str | Path],
) -> list[Path]:
    if isinstance(rawdata_source, (str, Path)):
        source_path = Path(rawdata_source)
        if source_path.is_dir():
            subdirs = [path for path in source_path.iterdir() if path.is_dir()]
            if subdirs:
                names = ", ".join(
                    path.name for path in sorted(subdirs, key=lambda p: p.name.lower())
                )
                raise ValueError(
                    f"rawData directory must be flat; found subdirectories: {names}"
                )
            return sorted(
                path
                for path in source_path.iterdir()
                if path.is_file() and path.suffix.lower() == ".npz"
            )
        return [source_path]
    return [Path(path) for path in rawdata_source]


def source_items(rawdata_source: RawDataSource) -> list[RawDataSourceItem]:
    if isinstance(rawdata_source, NamedRawDataItem):
        _validate_memory_filename(rawdata_source.filename)
        return [rawdata_source]
    if isinstance(rawdata_source, (str, Path)):
        return source_files(rawdata_source)
    output: list[RawDataSourceItem] = []
    for item in rawdata_source:
        if isinstance(item, NamedRawDataItem):
            _validate_memory_filename(item.filename)
            output.append(item)
        else:
            output.append(Path(item))
    return output


def _validate_memory_filename(filename: str) -> None:
    path = Path(str(filename))
    if (
        not str(filename)
        or path.name != str(filename)
        or path.suffix.lower() != ".npz"
        or "/" in str(filename)
        or "\\" in str(filename)
    ):
        raise ValueError(
            f"in-memory rawData name must be a direct .npz basename: {filename!r}"
        )
