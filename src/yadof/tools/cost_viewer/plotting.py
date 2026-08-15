"""Matplotlib rendering for cost-history analysis."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
from typing import Sequence

from ...config import load_config
from ...job_template import api as job_template_api
from .analysis import (
    _generation_regions,
    _hash_change_rows,
    _hypervolume_axis_ylim,
    _optimization_start_rows,
    _row_cell_edges,
    _scatter_alpha,
    _visible_pareto_mask,
    gaussian_kernel_smoother,
    hypervolume_series,
    is_pareto_efficient,
)
from .history import objective_names
from .style import (
    AVG_TREND_LINE_WIDTH,
    AXIS_LINE_WIDTH,
    EVENT_LINE_ALPHA,
    EVENT_LINE_LABELS,
    EVENT_LINE_WIDTH,
    GENERATION_LABEL_Y,
    GENERATION_LABEL_STAGGER,
    GENERATION_SHADE_ALPHA,
    GENERATION_SHADE_COLOR,
    GRID_LINE_WIDTH,
    HASH_LINE_COLOR,
    HASH_LINE_LABEL,
    HASH_LINE_STYLE,
    HV_BOUNDARY_LINE_ALPHA,
    HV_BOUNDARY_LINE_WIDTH,
    HV_LINE_COLOR,
    HV_SHADE_ALPHA,
    HV_SHADE_LABEL,
    OPT_LINE_COLOR,
    OPT_LINE_LABEL,
    OPT_LINE_STYLE,
    PARETO_EDGE_LINE_WIDTH,
    PARETO_MARKER_AREA,
    PLOT_COLORS,
    PLOT_DPI,
    PLOT_FIGSIZE,
    PLOT_FONT_SIZE,
    PLOT_GENERATION_FONT_SIZE,
    PLOT_LEGEND_EDGE_PAD,
    PLOT_LEGEND_FONT_SIZE,
    PLOT_LEGEND_FRAME_ALPHA,
    PLOT_LEGEND_GAP,
    PLOT_MARKERS,
    PLOT_TICK_FONT_SIZE,
    PLOT_TIGHT_LAYOUT_PAD,
    PLOT_TITLE_FONT_SIZE,
    SCATTER_EDGE_LINE_WIDTH,
    SCATTER_MARKER_SIZE,
    TREND_LINE_ALPHA,
)
from .types import ViewCostError, WorkspaceLike


def _draw_generation_regions(
    axis, regions: Sequence[tuple[int, float, float]]
) -> None:
    xaxis_transform = axis.get_xaxis_transform()
    for generation, left, right in regions:
        if generation % 2:
            axis.axvspan(
                left,
                right,
                facecolor=GENERATION_SHADE_COLOR,
                edgecolor="none",
                alpha=GENERATION_SHADE_ALPHA,
                zorder=0,
            )
        axis.text(
            (left + right) / 2.0,
            GENERATION_LABEL_Y
            - (GENERATION_LABEL_STAGGER if generation % 2 else 0.0),
            str(generation),
            transform=xaxis_transform,
            ha="center",
            va="top",
            color="black",
            fontsize=PLOT_GENERATION_FONT_SIZE,
            zorder=4,
        )


def _add_split_legends(axis, axes: Sequence[object]) -> None:
    data_legend: dict[str, object] = {}
    event_legend: dict[str, object] = {}
    for source_axis in axes:
        handles, labels = source_axis.get_legend_handles_labels()
        for handle, label in zip(handles, labels):
            target = (
                event_legend
                if label in EVENT_LINE_LABELS
                else data_legend
            )
            target.setdefault(label, handle)

    data_artist = None
    if data_legend:
        data_artist = axis.legend(
            list(data_legend.values()),
            list(data_legend.keys()),
            loc="lower left",
            bbox_to_anchor=(
                PLOT_LEGEND_EDGE_PAD,
                PLOT_LEGEND_EDGE_PAD,
            ),
            frameon=True,
            framealpha=PLOT_LEGEND_FRAME_ALPHA,
            fontsize=PLOT_LEGEND_FONT_SIZE,
            borderpad=0.3,
            borderaxespad=0.0,
            labelspacing=0.3,
            handletextpad=0.5,
        )
    if event_legend:
        event_x = PLOT_LEGEND_EDGE_PAD
        if data_artist is not None:
            axis.figure.canvas.draw()
            renderer = axis.figure.canvas.get_renderer()
            data_bbox = data_artist.get_window_extent(
                renderer
            ).transformed(axis.transAxes.inverted())
            event_x = data_bbox.x1 + PLOT_LEGEND_GAP
        axis.legend(
            list(event_legend.values()),
            list(event_legend.keys()),
            loc="lower left",
            bbox_to_anchor=(event_x, PLOT_LEGEND_EDGE_PAD),
            frameon=True,
            framealpha=PLOT_LEGEND_FRAME_ALPHA,
            fontsize=PLOT_LEGEND_FONT_SIZE,
            borderpad=0.3,
            borderaxespad=0.0,
            labelspacing=0.3,
            handletextpad=0.5,
        )
        if data_artist is not None:
            axis.add_artist(data_artist)


def _import_plot_modules():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        import numpy as np
        from cycler import cycler
    except ImportError as exc:
        raise ViewCostError(
            "matplotlib and cycler are required to render viewCost PNG output"
        ) from exc
    return plt, np, cycler


def plot_rows(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    output_path: str | Path | None = None,
    *,
    objective_api=job_template_api,
    resolved_objective_names: Sequence[str] | None = None,
) -> Path:
    """Render normalized costs and hypervolume into a PNG."""

    plt, np, cycler = _import_plot_modules()
    if output_path is None:
        output = (
            load_config(workspace).workspace.tool_output_dir
            / f"cost_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
    else:
        output = Path(output_path).expanduser()
        if not output.is_absolute():
            output = (
                load_config(workspace).workspace.tool_output_dir / output
            )
    output.parent.mkdir(parents=True, exist_ok=True)

    names = (
        [str(name) for name in resolved_objective_names]
        if resolved_objective_names is not None
        else objective_names(workspace, rows, objective_api)
    )
    x = np.asarray([row["row_number"] for row in rows], dtype=float)
    cost_matrix = np.asarray(
        [row["costs"] for row in rows], dtype=float
    )
    average = np.asarray(
        [row["average_cost"] for row in rows], dtype=float
    )
    raw_pareto = is_pareto_efficient(cost_matrix)
    pareto_mask = _visible_pareto_mask(raw_pareto, average)
    optimization_start_rows = _optimization_start_rows(rows)
    generation_regions = _generation_regions(rows)
    hash_change_rows = _hash_change_rows(rows)
    x_edges = _row_cell_edges(rows)
    hv_x, all_hv, generation_hv, _hv_reference = hypervolume_series(rows)

    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = PLOT_FONT_SIZE
    plt.rcParams["axes.linewidth"] = AXIS_LINE_WIDTH
    plt.rcParams["axes.prop_cycle"] = cycler("color", PLOT_COLORS)

    threshold = 1000
    markersize = (
        SCATTER_MARKER_SIZE
        if len(rows) <= threshold
        else max(
            1.0,
            SCATTER_MARKER_SIZE
            * math.sqrt(threshold / len(rows)),
        )
    )
    alpha = _scatter_alpha(len(rows), threshold=threshold)

    fig, ax1 = plt.subplots(figsize=PLOT_FIGSIZE)
    ax1.set_axisbelow(True)
    fixed_markersize_pareto = PARETO_MARKER_AREA
    border_size_multiplier = 1.5
    event_line_style = {
        "linewidth": EVENT_LINE_WIDTH,
        "alpha": EVENT_LINE_ALPHA,
        "dash_capstyle": "butt",
        "zorder": 0.7,
    }
    _draw_generation_regions(ax1, generation_regions)

    first_opt = True
    for _, start_x in optimization_start_rows:
        ax1.axvline(
            start_x,
            color=OPT_LINE_COLOR,
            label=OPT_LINE_LABEL if first_opt else None,
            linestyle=OPT_LINE_STYLE,
            **event_line_style,
        )
        first_opt = False

    first_hash = True
    for start_x in hash_change_rows:
        ax1.axvline(
            start_x,
            color=HASH_LINE_COLOR,
            label=HASH_LINE_LABEL if first_hash else None,
            linestyle=HASH_LINE_STYLE,
            **event_line_style,
        )
        first_hash = False

    for index, name in enumerate(names):
        color = PLOT_COLORS[index % len(PLOT_COLORS)]
        marker = PLOT_MARKERS[index % len(PLOT_MARKERS)]
        y = cost_matrix[:, index]
        ax1.scatter(
            x[~pareto_mask],
            y[~pareto_mask],
            label=None if np.any(pareto_mask) else name,
            marker=marker,
            edgecolors="none",
            facecolors=color,
            alpha=alpha,
            s=markersize**2,
        )
        if np.any(pareto_mask):
            ax1.scatter(
                x[pareto_mask],
                y[pareto_mask],
                marker=marker,
                edgecolors="white",
                facecolors="white",
                linewidths=0,
                s=(
                    math.sqrt(fixed_markersize_pareto)
                    * border_size_multiplier
                )
                ** 2,
                zorder=2,
            )
            ax1.scatter(
                x[pareto_mask],
                y[pareto_mask],
                label=name,
                marker=marker,
                edgecolors=color,
                facecolors="none",
                linewidths=PARETO_EDGE_LINE_WIDTH,
                s=fixed_markersize_pareto,
                zorder=3,
            )

    if len(x) == 1:
        fine_x = x.copy()
        local_avg = average.copy()
    else:
        fine_x = np.linspace(
            float(np.min(x)), float(np.max(x)), 600
        )
        avg_spacing = float(np.mean(np.diff(x)))
        sigma = max(
            1e-12,
            max(1, int(0.03 * len(x))) * avg_spacing / 3.0,
        )
        local_avg = gaussian_kernel_smoother(
            x, average, fine_x, sigma
        )

    ax1.plot(
        fine_x,
        local_avg,
        color="black",
        linewidth=AVG_TREND_LINE_WIDTH,
        alpha=TREND_LINE_ALPHA,
        linestyle="-",
        marker=None,
        zorder=1,
    )
    ax1.scatter(
        x[~pareto_mask],
        average[~pareto_mask],
        color="black",
        label=None if np.any(pareto_mask) else "avg. cost",
        marker="o",
        alpha=alpha,
        s=markersize**2,
        linewidths=SCATTER_EDGE_LINE_WIDTH,
    )
    if np.any(pareto_mask):
        ax1.scatter(
            x[pareto_mask],
            average[pareto_mask],
            facecolors="white",
            edgecolors="white",
            linewidths=0,
            marker="o",
            s=(
                math.sqrt(fixed_markersize_pareto)
                * border_size_multiplier
            )
            ** 2,
            zorder=2,
        )
        ax1.scatter(
            x[pareto_mask],
            average[pareto_mask],
            label="avg. cost",
            facecolors="none",
            edgecolors="black",
            linewidths=PARETO_EDGE_LINE_WIDTH,
            marker="o",
            s=fixed_markersize_pareto,
            zorder=3,
        )

    ax1.set_xlabel("Evaluation index", fontsize=PLOT_FONT_SIZE)
    ax1.set_ylabel("Costs", fontsize=PLOT_FONT_SIZE)
    ax1.set_xlim(float(x_edges[0]), float(x_edges[-1]))
    y_max = max(1.0, float(np.max(cost_matrix)) * 1.05)
    y_min = min(0.0, float(np.min(cost_matrix)) * 1.05)
    ax1.set_ylim(y_min, y_max)
    ax1.tick_params(
        axis="both",
        labelsize=PLOT_TICK_FONT_SIZE,
        width=AXIS_LINE_WIDTH,
    )
    ax1.grid(
        True,
        which="both",
        linestyle="--",
        linewidth=GRID_LINE_WIDTH,
        alpha=0.7,
    )

    ax2 = ax1.twinx()
    ax2.patch.set_visible(False)
    ax2.fill_between(
        hv_x,
        generation_hv,
        all_hv,
        facecolor=HV_LINE_COLOR,
        edgecolor="none",
        alpha=HV_SHADE_ALPHA,
        label=HV_SHADE_LABEL,
        zorder=0.8,
    )
    for boundary in (generation_hv, all_hv):
        ax2.plot(
            hv_x,
            boundary,
            color=HV_LINE_COLOR,
            linewidth=HV_BOUNDARY_LINE_WIDTH,
            alpha=HV_BOUNDARY_LINE_ALPHA,
            zorder=0.9,
        )
    ax2.set_ylabel(
        "Hypervolume (HV)",
        color=HV_LINE_COLOR,
        fontsize=PLOT_FONT_SIZE,
    )
    ax2.set_ylim(*_hypervolume_axis_ylim(all_hv, generation_hv))
    ax2.tick_params(
        axis="y",
        colors=HV_LINE_COLOR,
        labelsize=PLOT_TICK_FONT_SIZE,
        width=AXIS_LINE_WIDTH,
    )
    ax2.spines["right"].set_color(HV_LINE_COLOR)
    ax1.set_title(
        "Optimization costs and hypervolume from recorded_data",
        fontsize=PLOT_TITLE_FONT_SIZE,
    )

    fig.tight_layout(pad=PLOT_TIGHT_LAYOUT_PAD)
    _add_split_legends(ax1, (ax1, ax2))
    fig.savefig(output, dpi=PLOT_DPI)
    plt.close(fig)
    return output


__all__ = ["plot_rows"]
