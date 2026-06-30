"""Small helpers for validating task rawData ``.npz`` files.

The contract is intentionally generic: each item contains one main numeric
array plus metadata describing its shape and optional axis descriptors. Axis
names are descriptive only; framework code must not infer behavior from them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

RawDataItem = Mapping[str, object] | str | Path
RAWDATA_SCHEMA_VERSION = 1


class RawDataContractError(ValueError):
    def __init__(self, message: str, *, error_type: str = "contract_error") -> None:
        super().__init__(message)
        self.error_type = error_type


def load_rawdata_item(item: RawDataItem) -> dict[str, object]:
    if isinstance(item, (str, Path)):
        with np.load(item, allow_pickle=False) as data:
            return {key: data[key].copy() for key in data.files}
    return dict(item)


def parse_metadata(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    if isinstance(raw, np.ndarray):
        if raw.shape != ():
            raise RawDataContractError("rawData metadata array must be scalar")
        raw = raw.item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RawDataContractError("rawData metadata is not valid JSON") from exc
        if not isinstance(loaded, dict):
            raise RawDataContractError("rawData metadata JSON must be an object")
        return loaded
    if isinstance(raw, Mapping):
        return dict(raw)
    raise RawDataContractError(f"unsupported rawData metadata type: {type(raw).__name__}")


def metadata_from_item(item: Mapping[str, object]) -> dict[str, object]:
    return parse_metadata(item.get("metadata"))


def validate_rawdata_item(item: RawDataItem, *, require_metadata: bool = True) -> dict[str, object]:
    loaded = load_rawdata_item(item)
    metadata = metadata_from_item(loaded)
    if require_metadata and not metadata:
        raise RawDataContractError("rawData item must contain metadata", error_type="missing_metadata")
    if not metadata:
        return loaded

    _validate_schema_version(metadata)
    shape = _validate_declared_shape(loaded, metadata)
    _validate_declared_axes(loaded, metadata, shape)
    return loaded


def with_schema_version(metadata: Mapping[str, object]) -> dict[str, object]:
    updated = dict(metadata)
    updated["schema_version"] = RAWDATA_SCHEMA_VERSION
    return updated


def validate_rawdata_directory(rawdata_dir: str | Path) -> tuple[Path, ...]:
    directory = Path(rawdata_dir)
    if not directory.is_dir():
        raise RawDataContractError(f"rawData directory does not exist: {directory}")
    subdirs = [path for path in directory.iterdir() if path.is_dir()]
    if subdirs:
        names = ", ".join(path.name for path in sorted(subdirs, key=lambda p: p.name.lower()))
        raise RawDataContractError(f"rawData directory must be flat; found subdirectories: {names}")

    files = tuple(
        sorted(
            (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".npz"),
            key=lambda p: p.name.lower(),
        )
    )
    for path in files:
        validate_rawdata_item(path)
    return files


def _main_array_key(item: Mapping[str, object]) -> str:
    if "values" in item:
        return "values"
    if "data" in item:
        return "data"
    raise RawDataContractError("rawData item must contain a values or data array")


def _validate_schema_version(metadata: Mapping[str, object]) -> None:
    if "schema_version" not in metadata:
        raise RawDataContractError(
            "rawData metadata must contain schema_version",
            error_type="legacy_schema",
        )
    version = _metadata_int(metadata["schema_version"], "metadata schema_version")
    if version != RAWDATA_SCHEMA_VERSION:
        raise RawDataContractError(
            f"unsupported rawData schema_version: {version}",
            error_type="unsupported_schema_version",
        )


def _validate_declared_shape(item: Mapping[str, object], metadata: Mapping[str, object]) -> tuple[int, ...]:
    if "shape" not in metadata:
        raise RawDataContractError("rawData metadata must contain shape")
    data_key = _main_array_key(item)
    expected = _shape_tuple(metadata["shape"])
    actual = tuple(int(value) for value in np.asarray(item[data_key]).shape)
    if actual != expected:
        raise RawDataContractError(f"rawData {data_key!r} shape mismatch: metadata {expected}, actual {actual}")
    return expected


def _shape_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RawDataContractError("metadata shape must be a sequence of integers")
    shape = tuple(_metadata_int(item, "metadata shape entries") for item in value)
    if any(size < 0 for size in shape):
        raise RawDataContractError("metadata shape entries must be non-negative")
    return shape


def _metadata_int(value: object, label: str) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise RawDataContractError(f"{label} must be integers") from exc


def _validate_declared_axes(item: Mapping[str, object], metadata: Mapping[str, object], shape: tuple[int, ...]) -> None:
    axes = metadata.get("axes")
    if axes is None:
        return
    if not isinstance(axes, Sequence) or isinstance(axes, (str, bytes, Mapping)):
        raise RawDataContractError("metadata axes must be a sequence ordered by axis index")
    if len(axes) != len(shape):
        raise RawDataContractError(f"metadata axes length {len(axes)} does not match shape rank {len(shape)}")

    for expected_index, descriptor in enumerate(axes):
        if not isinstance(descriptor, Mapping):
            raise RawDataContractError("metadata axes entries must be objects")
        if "index" not in descriptor or "size" not in descriptor:
            raise RawDataContractError("metadata axis descriptors must contain index and size")

        axis_index = _metadata_int(descriptor["index"], "metadata axis index")
        if axis_index != expected_index:
            raise RawDataContractError(
                f"metadata axes must be ordered by index; expected {expected_index}, got {axis_index}"
            )

        axis_size = _metadata_int(descriptor["size"], "metadata axis size")
        if axis_size != shape[axis_index]:
            raise RawDataContractError(
                f"metadata axis {axis_index} size mismatch: metadata {axis_size}, shape {shape[axis_index]}"
            )

        values_key = descriptor.get("values_key")
        if values_key is None:
            continue
        if not isinstance(values_key, str) or not values_key:
            raise RawDataContractError(f"metadata axis {axis_index} values_key must be a non-empty string")
        if values_key not in item:
            raise RawDataContractError(f"metadata axis {axis_index} values_key {values_key!r} is missing")
        values = np.asarray(item[values_key])
        if values.ndim == 0 or int(values.shape[0]) != axis_size:
            raise RawDataContractError(
                f"metadata axis {axis_index} values length mismatch: expected {axis_size}, got {values.shape}"
            )
