"""Small helpers for validating task rawData ``.npz`` files.

The contract is intentionally generic: each item contains one main numeric
array plus metadata describing its shape and optional axis descriptors. Axis
names are descriptive only; framework code must not infer behavior from them.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np

RawDataItem = Mapping[str, object] | str | Path
AxisConverter = Callable[[np.ndarray, str], np.ndarray]
RAWDATA_SCHEMA_VERSION = 1


class RawDataContractError(ValueError):
    def __init__(self, message: str, *, error_type: str = "contract_error") -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class RawDataView:
    item: Mapping[str, object]
    metadata: Mapping[str, object]
    data_key: str
    data: np.ndarray
    axis_names: tuple[str, ...]
    axis_values: Mapping[str, np.ndarray]
    axis_units: Mapping[str, str]

    @classmethod
    def from_item(cls, item: RawDataItem) -> RawDataView:
        loaded = validate_rawdata_item(item)
        metadata = metadata_from_item(loaded)
        data_key = _main_array_key(loaded)
        axis_names = _axis_names_from_metadata(metadata)
        axis_values, axis_units = _axis_maps(loaded, metadata, axis_names)
        return cls(
            item=loaded,
            metadata=metadata,
            data_key=data_key,
            data=np.asarray(loaded[data_key]),
            axis_names=axis_names,
            axis_values=axis_values,
            axis_units=axis_units,
        )

    @property
    def name(self) -> str:
        return str(self.metadata.get("rawdata_name") or "")

    def has_axis(self, name: str) -> bool:
        return str(name) in self.axis_names

    def axis_index(self, name: str) -> int:
        try:
            return self.axis_names.index(str(name))
        except ValueError as exc:
            raise KeyError(name) from exc

    def axis(self, name: str) -> tuple[np.ndarray, str]:
        self.axis_index(name)
        return self.axis_values.get(name, np.asarray([], dtype=float)), self.axis_units.get(name, "")

    def axis_coordinates(self, name: str, converter: AxisConverter | None = None) -> np.ndarray:
        values, unit = self.axis(name)
        return values if converter is None else np.asarray(converter(values, unit), dtype=float)

    def nearest_index(
        self,
        name: str,
        target: float,
        tolerance: float,
        *,
        period: float | None = None,
        converter: AxisConverter | None = None,
    ) -> int:
        return _nearest_index(
            self.axis_coordinates(name, converter),
            target,
            tolerance,
            period=period,
        )

    def select(
        self,
        name: str,
        target: float,
        tolerance: float,
        *,
        period: float | None = None,
        converter: AxisConverter | None = None,
    ) -> RawDataView:
        axis = self.axis_index(name)
        index = self.nearest_index(name, target, tolerance, period=period, converter=converter)
        return RawDataView(
            item=self.item,
            metadata=self.metadata,
            data_key=self.data_key,
            data=np.take(self.data, index, axis=axis),
            axis_names=self.axis_names[:axis] + self.axis_names[axis + 1 :],
            axis_values={key: value for key, value in self.axis_values.items() if key != name},
            axis_units={key: value for key, value in self.axis_units.items() if key != name},
        )

    def range_indices(
        self,
        name: str,
        low: float,
        high: float,
        *,
        converter: AxisConverter | None = None,
    ) -> np.ndarray:
        coordinates = self.axis_coordinates(name, converter)
        lo, hi = sorted((float(low), float(high)))
        return np.flatnonzero(np.isfinite(coordinates) & (coordinates >= lo) & (coordinates <= hi))


def load_rawdata_views(items: Sequence[RawDataItem]) -> tuple[RawDataView, ...]:
    return tuple(RawDataView.from_item(item) for item in items)


def combine_2d_curves(
    items: Sequence[RawDataView],
    axis_name: str,
    converter: AxisConverter | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    x_chunks: list[np.ndarray] = []
    y_chunks: list[np.ndarray] = []
    for item in items:
        y = np.asarray(item.data).ravel()
        x = item.axis_coordinates(axis_name, converter)
        if x.size != y.size:
            raise ValueError(f"{item.name} {axis_name}/data size mismatch: {x.size} != {y.size}")
        x_chunks.append(x)
        y_chunks.append(y)
    if not x_chunks:
        raise ValueError("no 2D curve data")
    return np.concatenate(x_chunks), np.concatenate(y_chunks)


def frequency_to_ghz(values: np.ndarray, unit: str) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    scale = {"hz": 1e-9, "khz": 1e-6, "mhz": 1e-3, "ghz": 1.0}.get(unit.strip().lower())
    if scale is not None:
        return values * scale
    maximum = float(np.max(np.abs(values))) if values.size else 0.0
    return values * (1e-9 if maximum > 1e8 else 1e-6 if maximum > 1e5 else 1e-3 if maximum > 1e2 else 1.0)


def angle_to_degrees(values: np.ndarray, unit: str) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    unit_text = unit.strip().lower()
    if unit_text.startswith("rad") or (
        not unit_text and values.size and float(np.max(np.abs(values))) <= 2.0 * math.pi + 1e-9
    ):
        return np.degrees(values)
    return values


def mark_axis_range(
    weights: np.ndarray,
    item: RawDataView,
    axis_name: str,
    low: float,
    high: float,
    value: float,
    *,
    converter: AxisConverter | None = None,
) -> None:
    if not item.has_axis(axis_name):
        weights[...] = value
        return
    axis = item.axis_index(axis_name)
    coordinates = item.axis_coordinates(axis_name, converter)
    if coordinates.size != weights.shape[axis]:
        weights[...] = value
        return
    lo, hi = sorted((float(low), float(high)))
    mask = (coordinates >= lo) & (coordinates <= hi)
    if np.any(mask):
        index = [slice(None)] * weights.ndim
        index[axis] = mask
        weights[tuple(index)] = value


def mark_axis_points(
    weights: np.ndarray,
    item: RawDataView,
    axis_name: str,
    targets: Sequence[float],
    tolerance: float,
    value: float,
    *,
    period: float | None = None,
    converter: AxisConverter | None = None,
) -> None:
    if not item.has_axis(axis_name):
        if weights.size == len(targets):
            weights[...] = value
        return
    axis = item.axis_index(axis_name)
    coordinates = item.axis_coordinates(axis_name, converter)
    if coordinates.size != weights.shape[axis]:
        return
    indices = []
    for target in targets:
        try:
            indices.append(
                item.nearest_index(
                    axis_name,
                    float(target),
                    tolerance,
                    period=period,
                    converter=converter,
                )
            )
        except ValueError:
            continue
    if indices:
        index = [slice(None)] * weights.ndim
        index[axis] = np.asarray(sorted(set(indices)), dtype=int)
        weights[tuple(index)] = value


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


def _axis_names_from_metadata(metadata: Mapping[str, object]) -> tuple[str, ...]:
    raw_names = metadata.get("axis_names")
    if isinstance(raw_names, Sequence) and not isinstance(raw_names, (str, bytes, Mapping)):
        return tuple(str(name) for name in raw_names)
    axes = metadata.get("axes")
    if not isinstance(axes, Sequence) or isinstance(axes, (str, bytes, Mapping)):
        return ()
    return tuple(
        str(
            descriptor.get("name")
            or str(descriptor.get("values_key", index)).removeprefix("axis_")
        )
        if isinstance(descriptor, Mapping)
        else str(descriptor)
        for index, descriptor in enumerate(axes)
    )


def _axis_descriptor(metadata: Mapping[str, object], axis_index: int) -> Mapping[str, object]:
    axes = metadata.get("axes")
    if not isinstance(axes, Sequence) or isinstance(axes, (str, bytes, Mapping)) or axis_index >= len(axes):
        return {}
    descriptor = axes[axis_index]
    return descriptor if isinstance(descriptor, Mapping) else {}


def _axis_maps(
    item: Mapping[str, object],
    metadata: Mapping[str, object],
    axis_names: Sequence[str],
) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    values, units = {}, {}
    for axis_index, name in enumerate(axis_names):
        descriptor = _axis_descriptor(metadata, axis_index)
        values_key = str(descriptor.get("values_key") or f"axis_{name}")
        unit_key = str(descriptor.get("unit_key") or f"unit_{name}")
        values[name] = np.asarray(item.get(values_key, ()), dtype=float).ravel()
        units[name] = str(descriptor.get("unit") or _scalar_text(item.get(unit_key, "")))
    return values, units


def _scalar_text(value: object) -> str:
    array = np.asarray(value)
    return str(array.item()) if array.shape == () else str(value)


def _nearest_index(
    values: np.ndarray,
    target: float,
    tolerance: float,
    *,
    period: float | None = None,
) -> int:
    values = np.asarray(values, dtype=float).ravel()
    if values.size == 0:
        raise ValueError("empty axis")
    difference = values - float(target)
    if period is None:
        difference = np.abs(difference)
    else:
        period = abs(float(period))
        difference = np.minimum.reduce(
            (np.abs(difference), np.abs(difference - period), np.abs(difference + period))
        )
    index = int(np.argmin(difference))
    if float(difference[index]) > float(tolerance):
        raise ValueError("nearest axis point outside tolerance")
    return index


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
