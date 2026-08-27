from __future__ import annotations

from itertools import product
from typing import Sequence

import numpy as np

from .types import AxisEncoding, FieldLayout


def coordinate_feature_count(layout: FieldLayout) -> int:
    """Return the explicit encoded-coordinate width for one field."""

    return sum(
        2 if encoding.kind == "periodic" else 1
        for encoding in layout.axis_encodings
    )


def _strict_axis(values: np.ndarray, *, name: str) -> tuple[np.ndarray, bool]:
    axis = np.asarray(values, dtype=np.float64).reshape(-1)
    if axis.size == 0 or not np.all(np.isfinite(axis)):
        raise ValueError(f"coordinate axis {name!r} must be non-empty and finite")
    if axis.size == 1:
        return axis, False
    differences = np.diff(axis)
    if np.all(differences > 0):
        return axis, False
    if np.all(differences < 0):
        return axis[::-1].copy(), True
    raise ValueError(
        f"coordinate axis {name!r} must be strictly monotonic for readout"
    )


def _canonical_axis_query(
    values: np.ndarray,
    encoding: AxisEncoding,
    query: np.ndarray,
    *,
    name: str,
) -> tuple[np.ndarray, np.ndarray]:
    axis, _reversed = _strict_axis(values, name=name)
    requested = np.asarray(query, dtype=np.float64).reshape(-1)
    if not np.all(np.isfinite(requested)):
        raise ValueError(f"coordinate query for axis {name!r} must be finite")
    if encoding.kind == "periodic":
        assert encoding.period is not None
        origin = float(axis[0])
        requested = origin + np.mod(requested - origin, float(encoding.period))
        tolerance = np.finfo(np.float64).eps * max(
            32.0, abs(float(axis[-1])), abs(float(encoding.period))
        )
        requested = np.where(
            (requested > axis[-1]) & (requested <= axis[-1] + tolerance),
            axis[-1],
            requested,
        )
    tolerance = 1.0e-10 * max(
        1.0,
        abs(float(axis[0])),
        abs(float(axis[-1])),
    )
    if np.any(requested < axis[0] - tolerance) or np.any(
        requested > axis[-1] + tolerance
    ):
        raise ValueError(
            f"coordinate query for axis {name!r} is outside the stored domain"
        )
    return axis, np.clip(requested, axis[0], axis[-1])


def encode_coordinate_points(
    layout: FieldLayout, points: np.ndarray
) -> np.ndarray:
    """Encode physical points using only schema-declared axis semantics."""

    matrix = np.asarray(points, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != layout.rank:
        raise ValueError(
            f"coordinate points for {layout.selector!r} must have shape [Q,{layout.rank}]"
        )
    if not np.all(np.isfinite(matrix)):
        raise ValueError("coordinate points must be finite")
    if layout.rank == 0:
        return np.zeros((matrix.shape[0], 0), dtype=np.float32)
    features = []
    for axis_index, (name, values, encoding) in enumerate(
        zip(layout.axis_names, layout.axis_values, layout.axis_encodings)
    ):
        axis, query = _canonical_axis_query(
            values, encoding, matrix[:, axis_index], name=name
        )
        if encoding.kind == "log":
            if np.any(axis <= 0) or np.any(query <= 0):
                raise ValueError(
                    f"log coordinate encoding for axis {name!r} requires positive values"
                )
            axis = np.log(axis)
            query = np.log(query)
        if encoding.kind == "periodic":
            assert encoding.period is not None
            phase = (
                2.0
                * np.pi
                * (query - float(axis[0]))
                / float(encoding.period)
            )
            features.extend((np.sin(phase), np.cos(phase)))
            continue
        span = float(axis[-1] - axis[0])
        if span == 0.0:
            encoded = np.zeros_like(query)
        else:
            encoded = 2.0 * (query - float(axis[0])) / span - 1.0
        features.append(encoded)
    return np.ascontiguousarray(np.stack(features, axis=1), dtype=np.float32)


def coordinate_grid(
    layout: FieldLayout,
    axis_coordinates: Sequence[np.ndarray] | None = None,
) -> tuple[np.ndarray, tuple[int, ...], tuple[np.ndarray, ...]]:
    """Return Cartesian physical points, output shape, and copied query axes."""

    if axis_coordinates is None:
        axes = tuple(
            np.ascontiguousarray(values, dtype=np.float64)
            for values in layout.axis_values
        )
    else:
        if len(axis_coordinates) != layout.rank:
            raise ValueError(
                f"field {layout.selector!r} requires {layout.rank} coordinate axes"
            )
        axes = tuple(
            np.ascontiguousarray(np.asarray(values, dtype=np.float64).reshape(-1))
            for values in axis_coordinates
        )
    if any(values.size == 0 for values in axes):
        raise ValueError("coordinate query axes must be non-empty")
    if layout.rank == 0:
        points = np.zeros((1, 0), dtype=np.float64)
        return points, (), ()
    meshes = np.meshgrid(*axes, indexing="ij")
    points = np.ascontiguousarray(
        np.stack([values.reshape(-1) for values in meshes], axis=1),
        dtype=np.float64,
    )
    # Validation is centralized here so callers cannot bypass schema domains.
    encode_coordinate_points(layout, points)
    return points, tuple(int(values.size) for values in axes), axes


def stored_coordinate_points(layout: FieldLayout) -> np.ndarray:
    return coordinate_grid(layout)[0]


def interpolate_stored_values(
    layout: FieldLayout,
    stored_values: np.ndarray,
    points: np.ndarray,
) -> np.ndarray:
    """Multilinearly interpolate one stored-grid vector at physical points."""

    query = np.asarray(points, dtype=np.float64)
    if query.ndim != 2 or query.shape[1] != layout.rank:
        raise ValueError("interpolation coordinate rank does not match field layout")
    values = np.asarray(stored_values, dtype=np.float64).reshape(layout.shape)
    if layout.rank == 0:
        return np.full(query.shape[0], float(values), dtype=np.float64)

    axes = []
    grid = values
    canonical_query = []
    for axis_index, (name, raw_axis, encoding) in enumerate(
        zip(layout.axis_names, layout.axis_values, layout.axis_encodings)
    ):
        axis, reversed_axis = _strict_axis(raw_axis, name=name)
        if reversed_axis:
            grid = np.flip(grid, axis=axis_index)
        axis, requested = _canonical_axis_query(
            axis,
            encoding,
            query[:, axis_index],
            name=name,
        )
        axes.append(axis)
        canonical_query.append(requested)

    lower = []
    upper = []
    fractions = []
    for axis, requested in zip(axes, canonical_query):
        if axis.size == 1:
            low = high = np.zeros(requested.size, dtype=np.int64)
            fraction = np.zeros(requested.size, dtype=np.float64)
        else:
            high = np.searchsorted(axis, requested, side="right")
            high = np.clip(high, 1, axis.size - 1).astype(np.int64)
            low = high - 1
            denominator = axis[high] - axis[low]
            fraction = (requested - axis[low]) / denominator
            at_upper = requested == axis[-1]
            low[at_upper] = axis.size - 1
            high[at_upper] = axis.size - 1
            fraction[at_upper] = 0.0
        lower.append(low)
        upper.append(high)
        fractions.append(fraction)

    output = np.zeros(query.shape[0], dtype=np.float64)
    for corner in product((0, 1), repeat=layout.rank):
        indices = []
        weight = np.ones(query.shape[0], dtype=np.float64)
        for axis_index, choose_upper in enumerate(corner):
            indices.append(
                upper[axis_index] if choose_upper else lower[axis_index]
            )
            weight *= (
                fractions[axis_index]
                if choose_upper
                else 1.0 - fractions[axis_index]
            )
        output += weight * grid[tuple(indices)]
    return output


__all__ = [
    "coordinate_feature_count",
    "coordinate_grid",
    "encode_coordinate_points",
    "interpolate_stored_values",
    "stored_coordinate_points",
]
