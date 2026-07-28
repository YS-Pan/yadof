"""Matplotlib views used by the two GUI tabs."""

from __future__ import annotations

from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure
import numpy as np
import tkinter as tk
from tkinter import ttk

from ..backend import (
    ErrorMatrix,
    PredictionResult,
    SurrogateWorkspace,
    extract_curve,
    finite_curve_bounds,
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
        grid = self.figure.add_gridspec(2, 1, height_ratios=(3, 1.35))
        self.curve_ax = self.figure.add_subplot(grid[0, 0])
        self.cost_ax = self.figure.add_subplot(grid[1, 0])
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.draw_empty()

    def draw_empty(self) -> None:
        self.curve_ax.clear()
        self.cost_ax.clear()
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
    ) -> None:
        predicted_curve = extract_curve(result.predicted_sample, item_index)
        true_curve = (
            extract_curve(result.true_sample, item_index)
            if result.true_sample is not None
            else None
        )
        member_curves = tuple(
            extract_curve(sample, item_index)
            for sample in result.member_samples
        )
        bounds = finite_curve_bounds(member_curves)

        ax = self.curve_ax
        ax.clear()
        ax.set_axis_on()
        if bounds is not None:
            member_minimum, member_maximum = bounds
            ax.fill_between(
                predicted_curve.x,
                member_minimum,
                member_maximum,
                color=PREDICTION,
                alpha=0.16,
                linewidth=0,
                label="ensemble min–max",
            )
        ax.plot(
            predicted_curve.x,
            predicted_curve.y,
            color=PREDICTION,
            linewidth=2.2,
            label=(
                f"surrogate · checkpoint "
                f"{result.checkpoint_generation}"
            ),
        )
        if true_curve is not None:
            ax.plot(
                true_curve.x,
                true_curve.y,
                color=TRUTH,
                linewidth=2.0,
                linestyle="--",
                marker="o",
                markersize=3.5,
                label=f"real · {result.true_job_name}",
            )
        subtitle = (
            f" · {predicted_curve.slice_label}"
            if predicted_curve.slice_label
            else ""
        )
        ax.set_title(f"{predicted_curve.name}{subtitle}", loc="left")
        ax.set_xlabel(predicted_curve.x_label)
        ax.set_ylabel(predicted_curve.y_label)
        ax.grid(True, alpha=0.2)
        ax.legend(loc="best")

        cost_ax = self.cost_ax
        cost_ax.clear()
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
        self.canvas.draw_idle()


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
            edgecolors=PANEL,
            linewidth=1.0,
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
