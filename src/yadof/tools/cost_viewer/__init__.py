"""Reusable cost-history analysis and rendering package.

The package entry point stays free of eager Matplotlib imports so CLI startup
and future GUI discovery remain lightweight.
"""

from .analysis import hypervolume_series
from .api import view_cost
from .history import build_rows, objective_names
from .plotting import plot_rows
from .report import summarize_rows
from .types import ProgressCallback, ViewCostError, WorkspaceLike

__all__ = [
    "ProgressCallback",
    "ViewCostError",
    "WorkspaceLike",
    "build_rows",
    "hypervolume_series",
    "objective_names",
    "plot_rows",
    "summarize_rows",
    "view_cost",
]
