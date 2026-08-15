"""Shared contracts for the cost viewer."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...workspace import WorkspaceContext

WorkspaceLike = WorkspaceContext | str | Path
ProgressCallback = Callable[[int, int | None, str], None]


class ViewCostError(RuntimeError):
    """Raised when historical cost data cannot be visualized."""


__all__ = ["ProgressCallback", "ViewCostError", "WorkspaceLike"]
