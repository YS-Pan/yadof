"""Shared contracts for the cost viewer."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...workspace import WorkspaceContext

WorkspaceLike = WorkspaceContext | str | Path
ProgressCallback = Callable[[int, int | None, str], None]


class ProgressMessage(str):
    """Progress text with optional independent terminal-bar units.

    It remains a string for ordinary three-argument callbacks.  Renderers that
    understand the optional attributes may show a stable work-unit bar while the
    visible count uses a different unit.
    """

    def __new__(
        cls,
        value: str,
        *,
        bar_completed: int | None = None,
        bar_total: int | None = None,
    ) -> "ProgressMessage":
        result = super().__new__(cls, value)
        result.bar_completed = bar_completed
        result.bar_total = bar_total
        return result


class ViewCostError(RuntimeError):
    """Raised when historical cost data cannot be visualized."""


__all__ = [
    "ProgressCallback",
    "ProgressMessage",
    "ViewCostError",
    "WorkspaceLike",
]
