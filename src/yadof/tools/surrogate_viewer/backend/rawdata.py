"""rawData extraction, flattening, and display helpers."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np

from yadof.job_template.rawdata_contract import RawDataView
from yadof.surrogate.runtime import _finite_fill_matrix
from yadof.surrogate.types import RawDataSchema

from .types import CurveData


def copy_template(
    sample: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            str(key): value.copy() if isinstance(value, np.ndarray) else value
            for key, value in item.items()
        }
        for item in sample
    )


def rawdata_names(
    sample: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    names: list[str] = []
    for index, item in enumerate(sample):
        fallback = f"rawData {index}"
        try:
            name = RawDataView.from_item(item).name
        except (TypeError, ValueError, KeyError):
            name = fallback
        names.append(name or fallback)
    return tuple(names)


def flatten_samples_for_schema(
    schema: RawDataSchema,
    samples: Sequence[Sequence[Mapping[str, object]]],
) -> np.ndarray:
    """Flatten recorded rawData using exactly the checkpoint's modeled slots."""

    output = np.empty((len(samples), int(schema.flat_dim)), dtype=np.float64)
    for slot in schema.modeled_slots:
        rows = []
        for sample in samples:
            if slot.item_index >= len(sample):
                raise ValueError("recorded rawData is missing a checkpoint item")
            item = sample[slot.item_index]
            if slot.key not in item:
                raise ValueError(
                    f"recorded rawData item {slot.item_index} is missing "
                    f"{slot.key!r}"
                )
            values = np.asarray(item[slot.key], dtype=np.float64)
            if tuple(values.shape) != slot.shape:
                raise ValueError(
                    f"recorded rawData shape mismatch for item {slot.item_index}: "
                    f"{tuple(values.shape)} != {slot.shape}"
                )
            rows.append(values.reshape(-1))
        output[:, slot.start : slot.end] = _finite_fill_matrix(
            np.stack(rows, axis=0)
        )
    return np.ascontiguousarray(output, dtype=np.float64)


def summarize_errors_by_item(
    schema: RawDataSchema,
    errors: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate finite modeled-scalar errors for each rawData item."""

    row_count = int(errors.shape[0])
    sums = np.zeros((row_count, len(schema.templates)), dtype=np.float64)
    counts = np.zeros((row_count, len(schema.templates)), dtype=np.int64)
    for slot in schema.modeled_slots:
        slot_errors = errors[:, slot.start : slot.end]
        finite = np.isfinite(slot_errors)
        sums[:, slot.item_index] += np.sum(
            np.where(finite, slot_errors, 0.0),
            axis=1,
        )
        counts[:, slot.item_index] += np.sum(
            finite,
            axis=1,
            dtype=np.int64,
        )
    return sums, counts


def _nearest_zero_index(values: np.ndarray) -> int:
    finite = np.isfinite(values)
    if not np.any(finite):
        return 0
    indices = np.flatnonzero(finite)
    return int(indices[np.argmin(np.abs(values[finite]))])


def extract_curve(
    sample: Sequence[Mapping[str, object]],
    item_index: int,
) -> CurveData:
    """Extract a useful 1-D curve from a generic rawData item."""

    if not 0 <= int(item_index) < len(sample):
        raise IndexError(item_index)
    view = RawDataView.from_item(sample[int(item_index)])
    data = np.real(np.asarray(view.data)).astype(float, copy=False)
    name = view.name or f"rawData {item_index}"

    if data.ndim == 0:
        return CurveData(
            name=name,
            x=np.asarray([0.0]),
            y=np.asarray([float(data)]),
            x_label="index",
            y_label=name,
            slice_label="",
        )

    if view.axis_names:
        x_axis_name = "Freq" if view.has_axis("Freq") else view.axis_names[0]
        x_axis_index = view.axis_index(x_axis_name)
        x_values, x_unit = view.axis(x_axis_name)
        selected = data
        slice_parts: list[str] = []
        for axis_index in reversed(range(data.ndim)):
            if axis_index == x_axis_index:
                continue
            axis_name = (
                view.axis_names[axis_index]
                if axis_index < len(view.axis_names)
                else f"axis {axis_index}"
            )
            coordinates = view.axis_values.get(axis_name)
            if (
                coordinates is not None
                and len(coordinates) == data.shape[axis_index]
            ):
                selected_index = _nearest_zero_index(
                    np.asarray(coordinates, dtype=float)
                )
                unit = view.axis_units.get(axis_name, "")
                value = float(np.asarray(coordinates)[selected_index])
                suffix = f" {unit}" if unit else ""
                slice_parts.append(f"{axis_name}={value:g}{suffix}")
            else:
                selected_index = 0
                slice_parts.append(f"{axis_name}=index 0")
            selected = np.take(selected, selected_index, axis=axis_index)
            if axis_index < x_axis_index:
                x_axis_index -= 1
        y_values = np.asarray(selected, dtype=float).reshape(-1)
        x_values = np.asarray(x_values, dtype=float).reshape(-1)
        if x_values.size != y_values.size:
            x_values = np.arange(y_values.size, dtype=float)
            x_axis_name = "index"
            x_unit = ""
        x_label = f"{x_axis_name} ({x_unit})" if x_unit else x_axis_name
        return CurveData(
            name=name,
            x=x_values,
            y=y_values,
            x_label=x_label,
            y_label=name,
            slice_label=", ".join(reversed(slice_parts)),
        )

    values = data.reshape(-1)
    return CurveData(
        name=name,
        x=np.arange(values.size, dtype=float),
        y=values,
        x_label="index",
        y_label=name,
        slice_label="",
    )


def finite_curve_statistics(
    curves: Iterable[CurveData],
) -> tuple[np.ndarray, np.ndarray] | None:
    """Return pointwise ensemble mean/std when curves share coordinates."""

    rows = tuple(curves)
    if not rows:
        return None
    reference = rows[0].x
    if any(
        row.x.shape != reference.shape or not np.allclose(row.x, reference)
        for row in rows[1:]
    ):
        return None
    matrix = np.stack([row.y for row in rows], axis=0)
    return np.nanmean(matrix, axis=0), np.nanstd(matrix, axis=0)
