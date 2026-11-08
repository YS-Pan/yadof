"""Matplotlib views used by the two GUI tabs."""

from __future__ import annotations

from typing import Mapping

from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
import numpy as np
import tkinter as tk
from tkinter import ttk

from ..backend import (
    ErrorMatrix,
    PlotData,
    PredictionResult,
    SurrogateWorkspace,
    extract_plot,
    finite_plot_bounds,
)
from .style import MUTED, PANEL, PREDICTION, TEXT, TRUTH


class InteractivePlot(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.figure = Figure(
            figsize=(10, 7),
            dpi=100,
            constrained_layout=True,
        )
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.draw_empty()

    def _reset_axes(self, top_count: int = 1) -> list[object]:
        self.figure.clear()
        grid = self.figure.add_gridspec(2, 1, height_ratios=(3, 1.35))
        top_grid = grid[0, 0].subgridspec(1, top_count)
        top_axes = [
            self.figure.add_subplot(top_grid[0, index])
            for index in range(top_count)
        ]
        self.curve_ax = top_axes[0]
        self.cost_ax = self.figure.add_subplot(grid[1, 0])
        return top_axes

    def draw_empty(self) -> None:
        self._reset_axes()
        self.curve_ax.text(
            0.5,
            0.5,
            "Load a workspace to view surrogate predictions",
            ha="center",
            va="center",
            transform=self.curve_ax.transAxes,
            color=MUTED,
        )
        self.curve_ax.set_axis_off()
        self.cost_ax.set_axis_off()
        self.canvas.draw_idle()

    def draw_prediction(
        self,
        result: PredictionResult,
        workspace: SurrogateWorkspace,
        item_index: int,
        plotted_dimensions: tuple[int, ...],
        fixed_values: Mapping[int, float],
    ) -> None:
        if result.predicted_plot is None:
            predicted_plot = extract_plot(
                result.predicted_sample,
                item_index,
                plotted_dimensions,
                fixed_values,
            )
            true_plot = (
                extract_plot(
                    result.true_sample,
                    item_index,
                    plotted_dimensions,
                    fixed_values,
                )
                if result.true_sample is not None
                else None
            )
            member_plots = tuple(
                extract_plot(
                    sample,
                    item_index,
                    plotted_dimensions,
                    fixed_values,
                )
                for sample in result.member_samples
            )
        else:
            predicted_plot = result.predicted_plot
            true_plot = None
            member_plots = result.member_plots
        bounds = finite_plot_bounds(member_plots)
        top_axes = self._reset_axes(
            2 if predicted_plot.ndim == 2 and true_plot is not None else 1
        )
        if predicted_plot.ndim == 0:
            self._draw_scalar(
                top_axes[0],
                predicted_plot,
                true_plot,
                bounds,
                result,
            )
        elif predicted_plot.ndim == 1:
            self._draw_curve(
                top_axes[0],
                predicted_plot,
                true_plot,
                bounds,
                result,
            )
        else:
            self._draw_surfaces(
                top_axes,
                predicted_plot,
                true_plot,
                result,
            )
        if result.plot_note:
            self.figure.suptitle(
                result.plot_note,
                color=MUTED,
                fontsize=9,
            )
        self._draw_costs(result, workspace)
        self.canvas.draw_idle()

    @staticmethod
    def _title(plot: PlotData) -> str:
        subtitle = (
            f" · {plot.slice_label}"
            if plot.slice_label
            else ""
        )
        return f"{plot.name}{subtitle}"

    def _draw_scalar(
        self,
        ax: object,
        predicted: PlotData,
        truth: PlotData | None,
        bounds: tuple[np.ndarray, np.ndarray] | None,
        result: PredictionResult,
    ) -> None:
        predicted_value = float(predicted.values)
        ax.set_axis_on()
        ax.text(
            0.5,
            0.62,
            f"{predicted_value:.8g}",
            ha="center",
            va="center",
            transform=ax.transAxes,
            color=PREDICTION,
            fontsize=28,
            fontweight="semibold",
        )
        ax.text(
            0.5,
            0.46,
            f"surrogate · checkpoint {result.checkpoint_generation}",
            ha="center",
            va="center",
            transform=ax.transAxes,
            color=PREDICTION,
        )
        if bounds is not None:
            minimum, maximum = (
                float(np.asarray(value))
                for value in bounds
            )
            ax.text(
                0.5,
                0.36,
                f"ensemble min–max {minimum:.6g} … {maximum:.6g}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color=MUTED,
            )
        if truth is not None:
            ax.text(
                0.5,
                0.22,
                f"real · {result.true_job_name}: {float(truth.values):.8g}",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color=TRUTH,
                fontsize=13,
            )
        ax.set_title(self._title(predicted), loc="left")
        ax.set_xticks(())
        ax.set_yticks(())
        for spine in ax.spines.values():
            spine.set_visible(False)

    def _draw_curve(
        self,
        ax: object,
        predicted: PlotData,
        truth: PlotData | None,
        bounds: tuple[np.ndarray, np.ndarray] | None,
        result: PredictionResult,
    ) -> None:
        dimension = predicted.dimensions[0]
        if bounds is not None:
            member_minimum, member_maximum = bounds
            ax.fill_between(
                dimension.coordinates,
                member_minimum,
                member_maximum,
                color=PREDICTION,
                alpha=0.16,
                linewidth=0,
                label="ensemble min–max",
            )
        ax.plot(
            dimension.coordinates,
            predicted.values,
            color=PREDICTION,
            linewidth=2.2,
            label=(
                f"surrogate · checkpoint "
                f"{result.checkpoint_generation}"
            ),
        )
        if truth is not None:
            ax.plot(
                truth.dimensions[0].coordinates,
                truth.values,
                color=TRUTH,
                linewidth=2.0,
                linestyle="--",
                marker="o",
                markersize=3.5,
                label=f"real · {result.true_job_name}",
            )
        ax.set_title(self._title(predicted), loc="left")
        ax.set_xlabel(dimension.label)
        ax.set_ylabel(predicted.name)
        ax.grid(True, alpha=0.2)
        ax.legend(loc="best")

    def _draw_surfaces(
        self,
        axes: list[object],
        predicted: PlotData,
        truth: PlotData | None,
        result: PredictionResult,
    ) -> None:
        arrays = [predicted.values]
        if truth is not None:
            arrays.append(truth.values)
        finite_chunks = tuple(
            np.asarray(values)[np.isfinite(values)]
            for values in arrays
            if np.any(np.isfinite(values))
        )
        if finite_chunks:
            finite = np.concatenate(finite_chunks)
            low = float(np.min(finite))
            high = float(np.max(finite))
            if high <= low:
                high = low + max(abs(low) * 1e-6, 1e-12)
        else:
            low, high = 0.0, 1.0
        normalization = Normalize(vmin=low, vmax=high)
        artist = self._draw_surface(
            axes[0],
            predicted,
            normalization,
            (
                f"Surrogate · checkpoint "
                f"{result.checkpoint_generation}"
            ),
        )
        if truth is not None:
            self._draw_surface(
                axes[1],
                truth,
                normalization,
                f"Real · {result.true_job_name}",
            )
        colorbar = self.figure.colorbar(artist, ax=axes, pad=0.02)
        colorbar.set_label(predicted.name)
        axes[0].text(
            0.0,
            1.08,
            self._title(predicted),
            transform=axes[0].transAxes,
            ha="left",
            va="bottom",
            fontsize=12,
        )

    @staticmethod
    def _draw_surface(
        ax: object,
        plot: PlotData,
        normalization: Normalize,
        title: str,
    ) -> object:
        x_dimension, y_dimension = plot.dimensions
        values = np.ma.masked_invalid(np.asarray(plot.values).T)
        if (
            x_dimension.coordinates.size >= 2
            and y_dimension.coordinates.size >= 2
            and np.any(np.isfinite(plot.values))
        ):
            levels = np.linspace(
                normalization.vmin,
                normalization.vmax,
                64,
            )
            artist = ax.contourf(
                x_dimension.coordinates,
                y_dimension.coordinates,
                values,
                levels=levels,
                cmap="viridis",
                norm=normalization,
                antialiased=False,
            )
        else:
            artist = ax.pcolormesh(
                x_dimension.coordinates,
                y_dimension.coordinates,
                values,
                shading="nearest",
                cmap="viridis",
                norm=normalization,
                edgecolors="none",
            )
        ax.set_title(title, loc="left")
        ax.set_xlabel(x_dimension.label)
        ax.set_ylabel(y_dimension.label)
        return artist

    def _draw_costs(
        self,
        result: PredictionResult,
        workspace: SurrogateWorkspace,
    ) -> None:
        cost_ax = self.cost_ax
        names = workspace.objective_names
        positions = np.arange(len(names), dtype=float)
        if result.true_costs is None:
            cost_ax.bar(
                positions,
                result.predicted_costs,
                width=0.6,
                color=PREDICTION,
                label="surrogate",
            )
        else:
            width = 0.38
            cost_ax.bar(
                positions - width / 2,
                result.predicted_costs,
                width=width,
                color=PREDICTION,
                label="surrogate",
            )
            cost_ax.bar(
                positions + width / 2,
                result.true_costs,
                width=width,
                color=TRUTH,
                label="real",
            )
        cost_ax.set_title("Objective comparison", loc="left")
        cost_ax.set_xticks(positions)
        cost_ax.set_xticklabels(names, rotation=18, ha="right")
        cost_ax.set_ylabel("cost")
        cost_ax.grid(True, axis="y", alpha=0.2)
        cost_ax.legend(loc="best")


class HeatmapPlot(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.figure = Figure(
            figsize=(10, 7),
            dpi=100,
            constrained_layout=True,
        )
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.draw_empty()

    def draw_empty(self) -> None:
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self.ax.text(
            0.5,
            0.5,
            "This independent view predicts every optimization generation\n"
            "with every saved surrogate checkpoint.",
            ha="center",
            va="center",
            transform=self.ax.transAxes,
            color=MUTED,
        )
        self.ax.set_axis_off()
        self.canvas.draw_idle()

    def draw(self, matrix: ErrorMatrix) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        self.ax = ax
        column_count = len(matrix.checkpoint_generations)
        row_count = len(matrix.optimization_generations)
        x = np.arange(column_count, dtype=float)
        y = np.arange(row_count, dtype=float)
        x_edges = np.arange(column_count + 1, dtype=float) - 0.5
        y_edges = np.arange(row_count + 1, dtype=float) - 0.5
        masked = np.ma.masked_invalid(matrix.values)
        finite = matrix.values[np.isfinite(matrix.values)]
        if finite.size:
            low = float(np.min(finite))
            high = float(np.max(finite))
            if high <= low:
                high = low + max(abs(low) * 1e-6, 1e-12)
        else:
            low, high = 0.0, 1.0
        artist = ax.pcolormesh(
            x_edges,
            y_edges,
            masked,
            shading="flat",
            cmap="magma",
            vmin=low,
            vmax=high,
            edgecolors="none",
            linewidth=0.0,
            antialiased=False,
        )
        colorbar = self.figure.colorbar(artist, ax=ax, pad=0.02)
        colorbar.set_label(matrix.metric_label)
        ax.set_xticks(x, labels=matrix.checkpoint_generations)
        ax.set_yticks(y, labels=matrix.optimization_generations)
        ax.set_xlim(x_edges[0], x_edges[-1])
        ax.set_ylim(y_edges[0], y_edges[-1])
        ax.set_aspect("auto")
        ax.set_xlabel("Surrogate checkpoint generation")
        ax.set_ylabel("Optimization generation")
        ax.set_title(matrix.metric_label, loc="left")

        if matrix.values.size <= 120:
            midpoint = low + (high - low) * 0.58
            for row_index, row_position in enumerate(y):
                for column_index, column_position in enumerate(x):
                    value = matrix.values[row_index, column_index]
                    if not np.isfinite(value):
                        continue
                    display = (
                        f"{100.0 * value:.1f}%"
                        if matrix.metric_label.startswith("Mean relative")
                        else f"{value:.3g}"
                    )
                    ax.text(
                        column_position,
                        row_position,
                        display,
                        ha="center",
                        va="center",
                        fontsize=7,
                        color=TEXT if value >= midpoint else "white",
                        alpha=0.9,
                    )
        self.canvas.draw_idle()
