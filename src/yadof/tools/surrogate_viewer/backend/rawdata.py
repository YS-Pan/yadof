"""rawData extraction, flattening, and display helpers."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np

from yadof.job_template.rawdata_contract import RawDataView
from yadof.surrogate.conditional_inr.runtime import _finite_fill_matrix
from yadof.surrogate.conditional_inr.types import RawDataSchema

from .types import CurveData, DimensionSpec, PlotData


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


def rawdata_dimensions(
    sample: Sequence[Mapping[str, object]],
    item_index: int,
) -> tuple[DimensionSpec, ...]:
    """Describe every dimension of one rawData item in stored axis order."""

    if not 0 <= int(item_index) < len(sample):
        raise IndexError(item_index)
    view = RawDataView.from_item(sample[int(item_index)])
    dimensions: list[DimensionSpec] = []
    for axis_index, axis_size in enumerate(np.asarray(view.data).shape):
        name = (
            view.axis_names[axis_index]
            if axis_index < len(view.axis_names)
            and view.axis_names[axis_index]
            else f"axis {axis_index}"
        )
        coordinates = np.asarray(
            view.axis_values.get(name, ()),
            dtype=float,
        ).reshape(-1)
        unit = view.axis_units.get(name, "")
        if (
            coordinates.size != int(axis_size)
            or not np.all(np.isfinite(coordinates))
        ):
            coordinates = np.arange(axis_size, dtype=float)
            unit = ""
        dimensions.append(
            DimensionSpec(
                index=axis_index,
                name=name,
                coordinates=coordinates,
                unit=unit,
            )
        )
    return tuple(dimensions)


def extract_plot(
    sample: Sequence[Mapping[str, object]],
    item_index: int,
    plotted_dimensions: Sequence[int] = (),
    fixed_values: Mapping[int, float] | None = None,
) -> PlotData:
    """Extract a user-selected 0-D, 1-D, or 2-D slice."""

    if not 0 <= int(item_index) < len(sample):
        raise IndexError(item_index)
    view = RawDataView.from_item(sample[int(item_index)])
    data = np.real(np.asarray(view.data)).astype(float, copy=False)
    dimensions = rawdata_dimensions(sample, item_index)
    selected = tuple(int(index) for index in plotted_dimensions)
    if len(selected) > 2:
        raise ValueError("choose at most two plot dimensions")
    if len(set(selected)) != len(selected):
        raise ValueError("plot dimensions must be unique")
    if any(index < 0 or index >= data.ndim for index in selected):
        raise IndexError("plot dimension is outside the rawData rank")

    requested_fixed = fixed_values or {}
    indexer: list[object] = []
    fixed_parts: list[str] = []
    for dimension in dimensions:
        if dimension.index in selected:
            indexer.append(slice(None))
            continue
        target = float(requested_fixed.get(dimension.index, 0.0))
        actual = dimension.nearest_value(target)
        coordinate_index = int(
            np.argmin(np.abs(dimension.coordinates - actual))
        )
        indexer.append(coordinate_index)
        suffix = f" {dimension.unit}" if dimension.unit else ""
        fixed_parts.append(f"{dimension.name}={actual:g}{suffix}")

    values = np.asarray(data[tuple(indexer)], dtype=float)
    natural_order = tuple(sorted(selected))
    if selected and selected != natural_order:
        permutation = tuple(natural_order.index(index) for index in selected)
        values = np.transpose(values, axes=permutation)
    return PlotData(
        name=view.name or f"rawData {item_index}",
        dimensions=tuple(dimensions[index] for index in selected),
        values=values,
        slice_label=", ".join(fixed_parts),
    )


def plot_from_coordinate_grid(
    *,
    name: str,
    dimensions: Sequence[DimensionSpec],
    values: np.ndarray,
    plotted_dimensions: Sequence[int],
    fixed_values: Mapping[int, float],
) -> PlotData:
    """Build PlotData from a grid whose fixed dimensions have length one."""

    selected = tuple(int(index) for index in plotted_dimensions)
    array = np.asarray(values, dtype=float)
    if array.ndim != len(dimensions):
        raise ValueError("coordinate grid rank does not match rawData dimensions")
    indexer: list[object] = []
    fixed_parts: list[str] = []
    for dimension in dimensions:
        if dimension.index in selected:
            indexer.append(slice(None))
            continue
        indexer.append(0)
        value = float(fixed_values[dimension.index])
        suffix = f" {dimension.unit}" if dimension.unit else ""
        fixed_parts.append(f"{dimension.name}={value:g}{suffix}")

    plotted = np.asarray(array[tuple(indexer)], dtype=float)
    natural_order = tuple(sorted(selected))
    if selected and selected != natural_order:
        permutation = tuple(natural_order.index(index) for index in selected)
        plotted = np.transpose(plotted, axes=permutation)
    return PlotData(
        name=str(name),
        dimensions=tuple(dimensions[index] for index in selected),
        values=plotted,
        slice_label=", ".join(fixed_parts),
    )


def extract_curve(
    sample: Sequence[Mapping[str, object]],
    item_index: int,
) -> CurveData:
    """Extract a useful 1-D curve from a generic rawData item."""

    dimensions = rawdata_dimensions(sample, item_index)
    if not dimensions:
        plot = extract_plot(sample, item_index)
        return CurveData(
            name=plot.name,
            x=np.asarray([0.0]),
            y=np.asarray([float(plot.values)]),
            x_label="index",
            y_label=plot.name,
            slice_label="",
        )

    preferred = next(
        (
            dimension.index
            for dimension in dimensions
            if dimension.name.casefold() == "freq"
        ),
        dimensions[0].index,
    )
    plot = extract_plot(sample, item_index, (preferred,))
    dimension = plot.dimensions[0]
    return CurveData(
        name=plot.name,
        x=dimension.coordinates,
        y=np.asarray(plot.values, dtype=float),
        x_label=dimension.label,
        y_label=plot.name,
        slice_label=plot.slice_label,
    )


def _finite_bounds(
    rows: Sequence[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.stack(rows, axis=0)
    finite = np.isfinite(matrix)
    valid = np.any(finite, axis=0)
    lower = np.min(np.where(finite, matrix, np.inf), axis=0)
    upper = np.max(np.where(finite, matrix, -np.inf), axis=0)
    return (
        np.where(valid, lower, np.nan),
        np.where(valid, upper, np.nan),
    )


def finite_plot_bounds(
    plots: Iterable[PlotData],
) -> tuple[np.ndarray, np.ndarray] | None:
    """Return finite ensemble min/max for plots with shared dimensions."""

    rows = tuple(plots)
    if not rows:
        return None
    reference = rows[0]
    if any(
        row.ndim != reference.ndim
        or row.values.shape != reference.values.shape
        or any(
            candidate.coordinates.shape != expected.coordinates.shape
            or not np.allclose(candidate.coordinates, expected.coordinates)
            for candidate, expected in zip(
                row.dimensions,
                reference.dimensions,
            )
        )
        for row in rows[1:]
    ):
        return None
    return _finite_bounds(tuple(row.values for row in rows))


def finite_curve_bounds(
    curves: Iterable[CurveData],
) -> tuple[np.ndarray, np.ndarray] | None:
    """Return pointwise finite ensemble min/max for shared coordinates."""

    rows = tuple(curves)
    if not rows:
        return None
    reference = rows[0].x
    if any(
        row.x.shape != reference.shape or not np.allclose(row.x, reference)
        for row in rows[1:]
    ):
        return None
    return _finite_bounds(tuple(row.y for row in rows))
