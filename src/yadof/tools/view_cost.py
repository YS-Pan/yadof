"""Compatibility facade for :mod:`yadof.tools.cost_viewer`.

New integrations should import the ``cost_viewer`` package.  This module keeps
the established import path working for callers that used ``tools.view_cost``.
"""

from .cost_viewer import (
    ViewCostError,
    build_rows,
    hypervolume_series,
    objective_names,
    plot_rows,
    summarize_rows,
    view_cost,
)
from .cost_viewer.analysis import (
    _generation_groups,
    _generation_regions,
    _hash_change_rows,
    _hypervolume_axis_ylim,
    _optimization_start_rows,
    _row_cell_edges,
    _scatter_alpha,
    _visible_pareto_mask,
    gaussian_kernel_smoother,
    is_pareto_efficient,
)
from .cost_viewer.plotting import (
    _add_split_legends,
    _draw_generation_regions,
)
from .cost_viewer.style import (
    AVG_TREND_LINE_WIDTH,
    AXIS_LINE_WIDTH,
    EVENT_DASH_LENGTH,
    EVENT_LINE_ALPHA,
    EVENT_LINE_LABELS,
    EVENT_LINE_WIDTH,
    GENERATION_LABEL_Y,
    GENERATION_SHADE_ALPHA,
    GENERATION_SHADE_COLOR,
    GRID_LINE_WIDTH,
    HASH_LINE_COLOR,
    HASH_LINE_LABEL,
    HASH_LINE_STYLE,
    HV_LINE_COLOR,
    HV_SHADE_ALPHA,
    MAX_REPORTED_ISSUES,
    MAX_VISIBLE_PARETO,
    MIN_SCATTER_ALPHA,
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
    SCATTER_ALPHA,
    SCATTER_EDGE_LINE_WIDTH,
    SCATTER_MARKER_SIZE,
    TREND_LINE_ALPHA,
    TREND_LINE_WIDTH,
)

__all__ = [
    "ViewCostError",
    "build_rows",
    "hypervolume_series",
    "objective_names",
    "plot_rows",
    "summarize_rows",
    "view_cost",
]
