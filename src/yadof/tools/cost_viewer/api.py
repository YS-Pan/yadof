"""Public orchestration API for the cost viewer."""

from __future__ import annotations

from pathlib import Path

from ...config import load_config
from .history import build_rows
from .plotting import plot_rows
from .report import summarize_rows
from .types import ProgressCallback, WorkspaceLike


def view_cost(
    workspace: WorkspaceLike,
    *,
    status: str | None = "completed",
    output_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[str, Path | None]:
    """Return a dynamic-cost summary and optionally render a PNG."""

    config = load_config(workspace)
    issues: list[str] = []
    resolved_objective_names: list[str] = []
    rows = build_rows(
        config.workspace,
        status=status,
        issues=issues,
        progress=progress,
        objective_names_out=resolved_objective_names,
    )
    summary = summarize_rows(
        config.workspace,
        rows,
        issues=issues,
        resolved_objective_names=resolved_objective_names,
    )
    output = (
        None
        if output_path is None
        else plot_rows(
            config.workspace,
            rows,
            output_path,
            resolved_objective_names=resolved_objective_names,
        )
    )
    return summary, output


__all__ = ["view_cost"]
