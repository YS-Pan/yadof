"""Pure Matplotlib/Agg rendering for exported case-inspection evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np


def _axis_label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit else name


def _finite_limits(*arrays: np.ndarray | None) -> tuple[float, float]:
    finite_rows = [
        np.asarray(array, dtype=float)[np.isfinite(array)]
        for array in arrays
        if array is not None
    ]
    finite_rows = [row for row in finite_rows if row.size]
    if not finite_rows:
        return 0.0, 1.0
    values = np.concatenate(finite_rows)
    lower = float(np.min(values))
    upper = float(np.max(values))
    if lower == upper:
        padding = max(1.0, abs(lower)) * 1e-6
        return lower - padding, upper + padding
    return lower, upper


def _draw_objectives(axis: object, objectives: Sequence[Mapping[str, object]]) -> None:
    names = [str(item.get("name", "objective")) for item in objectives]
    predicted = np.asarray(
        [
            np.nan if item.get("predicted") is None else float(item["predicted"])
            for item in objectives
        ],
        dtype=float,
    )
    truth = np.asarray(
        [
            np.nan if item.get("true") is None else float(item["true"])
            for item in objectives
        ],
        dtype=float,
    )
    positions = np.arange(len(names), dtype=float)
    width = 0.38
    axis.bar(positions - width / 2, predicted, width, label="prediction")
    if np.any(np.isfinite(truth)):
        axis.bar(positions + width / 2, truth, width, label="truth")
    axis.set_xticks(positions, names, rotation=20, ha="right")
    axis.set_ylabel("current objective")
    axis.set_title("Objective comparison")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="best")


def render_case_plot(
    path: str | Path,
    *,
    dimension_names: Sequence[str],
    dimension_units: Sequence[str],
    coordinates: Sequence[np.ndarray],
    prediction: np.ndarray,
    truth: np.ndarray | None,
    ensemble_minimum: np.ndarray | None,
    ensemble_maximum: np.ndarray | None,
    objectives: Sequence[Mapping[str, object]],
    title: str,
) -> None:
    """Render one 0-D, 1-D, or 2-D diagnostic without a GUI backend."""

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    names = tuple(str(name) for name in dimension_names)
    units = tuple(str(unit) for unit in dimension_units)
    axes_coordinates = tuple(
        np.asarray(values, dtype=float).reshape(-1)
        for values in coordinates
    )
    predicted = np.asarray(prediction, dtype=float)
    actual = None if truth is None else np.asarray(truth, dtype=float)
    minimum = (
        None
        if ensemble_minimum is None
        else np.asarray(ensemble_minimum, dtype=float)
    )
    maximum = (
        None
        if ensemble_maximum is None
        else np.asarray(ensemble_maximum, dtype=float)
    )
    rank = len(axes_coordinates)
    if rank not in {0, 1, 2}:
        raise ValueError("case plots support only zero, one, or two dimensions")
    if len(names) != rank or len(units) != rank:
        raise ValueError("plot dimension metadata is not aligned")

    if rank == 2:
        panels = 1 + int(actual is not None) + int(
            minimum is not None and maximum is not None
        )
        figure = Figure(
            figsize=(max(9.0, 4.4 * panels), 8.0),
            constrained_layout=True,
        )
        canvas = FigureCanvasAgg(figure)
        grid = figure.add_gridspec(2, panels, height_ratios=(3.0, 1.25))
        raw_axes = [figure.add_subplot(grid[0, index]) for index in range(panels)]
        objective_axis = figure.add_subplot(grid[1, :])
        x, y = axes_coordinates
        if predicted.shape != (x.size, y.size):
            raise ValueError("two-dimensional prediction shape does not match coordinates")
        vmin, vmax = _finite_limits(predicted, actual)
        images = []
        images.append(
            raw_axes[0].pcolormesh(
                x,
                y,
                np.ma.masked_invalid(predicted.T),
                shading="auto",
                cmap="viridis",
                vmin=vmin,
                vmax=vmax,
            )
        )
        raw_axes[0].set_title("Prediction")
        next_panel = 1
        shared_axes = [raw_axes[0]]
        if actual is not None:
            if actual.shape != predicted.shape:
                raise ValueError("two-dimensional truth shape does not match prediction")
            raw_axes[next_panel].pcolormesh(
                x,
                y,
                np.ma.masked_invalid(actual.T),
                shading="auto",
                cmap="viridis",
                vmin=vmin,
                vmax=vmax,
            )
            raw_axes[next_panel].set_title("Truth")
            shared_axes.append(raw_axes[next_panel])
            next_panel += 1
        figure.colorbar(images[0], ax=shared_axes, label="rawData value")
        if minimum is not None and maximum is not None:
            spread = np.asarray(maximum - minimum, dtype=float)
            if spread.shape != predicted.shape:
                raise ValueError("ensemble range shape does not match prediction")
            spread_image = raw_axes[next_panel].pcolormesh(
                x,
                y,
                np.ma.masked_invalid(spread.T),
                shading="auto",
                cmap="magma",
                vmin=0.0,
            )
            raw_axes[next_panel].set_title("Ensemble range (max − min)")
            figure.colorbar(
                spread_image,
                ax=raw_axes[next_panel],
                label="range",
            )
        for axis in raw_axes:
            axis.set_xlabel(_axis_label(names[0], units[0]))
            axis.set_ylabel(_axis_label(names[1], units[1]))
        _draw_objectives(objective_axis, objectives)
    else:
        figure = Figure(figsize=(11.0, 8.0), constrained_layout=True)
        canvas = FigureCanvasAgg(figure)
        grid = figure.add_gridspec(2, 1, height_ratios=(3.0, 1.35))
        raw_axis = figure.add_subplot(grid[0, 0])
        objective_axis = figure.add_subplot(grid[1, 0])
        if rank == 1:
            x = axes_coordinates[0]
            y = predicted.reshape(-1)
            if x.size != y.size:
                raise ValueError("curve prediction shape does not match coordinates")
            if minimum is not None and maximum is not None:
                low = minimum.reshape(-1)
                high = maximum.reshape(-1)
                if low.size != x.size or high.size != x.size:
                    raise ValueError("curve ensemble range is not aligned")
                raw_axis.fill_between(
                    x,
                    low,
                    high,
                    color="#8ecae6",
                    alpha=0.35,
                    label="ensemble min/max",
                )
            raw_axis.plot(x, y, color="#1261a0", linewidth=1.7, label="prediction")
            if actual is not None:
                actual_curve = actual.reshape(-1)
                if actual_curve.size != x.size:
                    raise ValueError("curve truth shape does not match coordinates")
                raw_axis.plot(
                    x,
                    actual_curve,
                    color="#d1495b",
                    linewidth=1.35,
                    label="truth",
                )
            raw_axis.set_xlabel(_axis_label(names[0], units[0]))
            raw_axis.set_ylabel("rawData value")
        else:
            labels = ["prediction"]
            values = [float(predicted.reshape(()))]
            if actual is not None:
                labels.append("truth")
                values.append(float(actual.reshape(())))
            positions = np.arange(len(labels), dtype=float)
            raw_axis.bar(positions, values, width=0.58, color=("#1261a0", "#d1495b")[:len(labels)])
            if minimum is not None and maximum is not None:
                center = values[0]
                low = float(minimum.reshape(()))
                high = float(maximum.reshape(()))
                if np.isfinite(center) and np.isfinite(low) and np.isfinite(high):
                    raw_axis.errorbar(
                        [positions[0]],
                        [center],
                        yerr=[
                            [max(0.0, center - low)],
                            [max(0.0, high - center)],
                        ],
                        fmt="none",
                        ecolor="#023047",
                        capsize=6,
                        label="ensemble min/max",
                    )
            raw_axis.set_xticks(positions, labels)
            raw_axis.set_ylabel("rawData value")
        raw_axis.set_title("Selected rawData slice")
        raw_axis.grid(axis="y", alpha=0.25)
        handles, _labels = raw_axis.get_legend_handles_labels()
        if handles:
            raw_axis.legend(loc="best")
        _draw_objectives(objective_axis, objectives)

    figure.suptitle(str(title), fontsize=12)
    try:
        canvas.draw()
        figure.savefig(Path(path), format="png", dpi=150)
    finally:
        figure.clear()


__all__ = ["render_case_plot"]
