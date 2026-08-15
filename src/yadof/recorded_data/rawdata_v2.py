"""Owned no-pickle rawData conversion used by finalizers and v2 segments."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from ..job_template.rawdata_contract import (
    NamedRawDataItem,
    metadata_from_item,
    validate_rawdata_item,
)


RawDataSource = (
    str
    | Path
    | NamedRawDataItem
    | Sequence[str | Path | NamedRawDataItem]
)


def own_rawdata_source(source: RawDataSource) -> tuple[NamedRawDataItem, ...]:
    """Load and validate a source once, returning candidate-owned array copies."""

    output: list[NamedRawDataItem] = []
    seen: set[str] = set()
    for item in source_items(source):
        filename = item.filename if isinstance(item, NamedRawDataItem) else item.name
        _validate_filename(filename)
        folded = filename.casefold()
        if folded in seen:
            raise ValueError(f"duplicate rawData basename: {filename!r}")
        seen.add(folded)
        if isinstance(item, NamedRawDataItem):
            loaded = validate_rawdata_item(item.payload)
        else:
            with np.load(item, allow_pickle=False) as archive:
                loaded = validate_rawdata_item(
                    {name: archive[name].copy() for name in archive.files}
                )
        payload = {
            str(name): _owned_value(value, filename=filename, field=str(name))
            for name, value in loaded.items()
        }
        output.append(NamedRawDataItem(filename, payload))
    return tuple(output)


def encode_npz(item: NamedRawDataItem) -> bytes:
    """Encode one validated owned item without pickle."""

    validated = validate_rawdata_item(item.payload)
    arrays: dict[str, np.ndarray] = {}
    for key, value in validated.items():
        if key == "metadata":
            arrays[key] = np.asarray(
                json.dumps(
                    metadata_from_item(validated),
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            continue
        array = np.asarray(value)
        if array.dtype.hasobject:
            raise ValueError(
                f"rawData {item.filename!r} field {key!r} would require pickle"
            )
        arrays[str(key)] = array
    buffer = BytesIO()
    np.savez_compressed(buffer, **arrays)
    return buffer.getvalue()


def decode_npz(payload: bytes) -> dict[str, object]:
    """Decode and validate one ZIP member, including its inner NPZ checks."""

    with np.load(BytesIO(payload), allow_pickle=False) as archive:
        loaded = {name: archive[name].copy() for name in archive.files}
    return validate_rawdata_item(loaded)


def reservation_bytes(
    items: Sequence[NamedRawDataItem], metadata_bytes: int = 0
) -> int:
    """Conservatively reserve source plus one simultaneous encoding buffer."""

    resident = int(metadata_bytes)
    for item in items:
        resident += len(item.filename.encode("utf-8"))
        for value in item.payload.values():
            if isinstance(value, np.ndarray):
                resident += int(value.nbytes)
            elif isinstance(value, bytes):
                resident += len(value)
            elif isinstance(value, str):
                resident += len(value.encode("utf-8"))
            else:
                resident += 128
    return max(4096, resident * 2 + 64 * 1024)


def source_items(
    source: RawDataSource,
) -> tuple[Path | NamedRawDataItem, ...]:
    if isinstance(source, NamedRawDataItem):
        return (source,)
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_dir():
            subdirs = tuple(item for item in path.iterdir() if item.is_dir())
            if subdirs:
                raise ValueError("rawData directory must be flat")
            return tuple(
                sorted(
                    (
                        item
                        for item in path.iterdir()
                        if item.is_file() and item.suffix.lower() == ".npz"
                    ),
                    key=lambda item: item.name.casefold(),
                )
            )
        return (path,)
    return tuple(
        item if isinstance(item, NamedRawDataItem) else Path(item)
        for item in source
    )


def _owned_value(value: object, *, filename: str, field: str) -> object:
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise ValueError(
                f"rawData {filename!r} field {field!r} would require pickle"
            )
        return value.copy()
    if isinstance(value, Mapping):
        return {
            str(key): _owned_value(item, filename=filename, field=field)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [
            _owned_value(item, filename=filename, field=field) for item in value
        ]
    return value


def _validate_filename(filename: str) -> None:
    path = Path(str(filename))
    if (
        not str(filename)
        or path.name != str(filename)
        or path.suffix.lower() != ".npz"
        or "/" in str(filename)
        or "\\" in str(filename)
    ):
        raise ValueError(
            f"rawData name must be a direct .npz basename: {filename!r}"
        )


__all__ = [
    "RawDataSource",
    "decode_npz",
    "encode_npz",
    "own_rawdata_source",
    "reservation_bytes",
    "source_items",
]
