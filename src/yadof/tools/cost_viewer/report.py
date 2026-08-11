"""Terminal-friendly cost-history reports."""

from __future__ import annotations

from typing import Sequence

from .analysis import is_pareto_efficient, _visible_pareto_mask
from .history import objective_names
from .style import MAX_REPORTED_ISSUES, MAX_VISIBLE_PARETO
from .types import WorkspaceLike


def _ascii(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _table_lines(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    right_align: Sequence[bool],
) -> list[str]:
    widths = [len(text) for text in headers]
    for row in rows:
        for index, text in enumerate(row):
            widths[index] = max(widths[index], len(text))

    def format_row(row: Sequence[str]) -> str:
        return "  ".join(
            text.rjust(widths[index])
            if right_align[index]
            else text.ljust(widths[index])
            for index, text in enumerate(row)
        )

    return [
        format_row(headers),
        "  ".join("-" * width for width in widths),
        *(format_row(row) for row in rows),
    ]


def summarize_rows(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    *,
    max_pareto: int = MAX_VISIBLE_PARETO,
    objective_api=None,
    issues: Sequence[str] = (),
) -> str:
    """Format the compact CLI summary and Pareto table."""

    import numpy as np

    names = (
        objective_names(workspace, rows)
        if objective_api is None
        else objective_names(workspace, rows, objective_api)
    )
    cost_matrix = np.asarray(
        [row["costs"] for row in rows], dtype=float
    )
    average = np.asarray(
        [row["average_cost"] for row in rows], dtype=float
    )
    raw_pareto = is_pareto_efficient(cost_matrix)
    pareto_mask = _visible_pareto_mask(raw_pareto, average)
    if int(np.sum(pareto_mask)) > max_pareto:
        pareto_mask = _visible_pareto_mask(raw_pareto, average)

    lines = [
        f"rows: {len(rows)}",
        f"ignored issues: {len(issues)}",
        *(
            f"  - {_ascii(issue)}"
            for issue in issues[:MAX_REPORTED_ISSUES]
        ),
        *(
            [f"  - ... {len(issues) - MAX_REPORTED_ISSUES} more"]
            if len(issues) > MAX_REPORTED_ISSUES
            else []
        ),
        "Pareto front shown: "
        f"{int(np.sum(pareto_mask))} of {int(np.sum(raw_pareto))}",
        "Pareto front:",
    ]
    headers = [
        "row",
        *[_ascii(name) for name in names],
        "avg. cost",
        "job_name",
    ]
    table_rows = [
        [
            str(int(rows[index]["row_number"])),
            *(
                f"{float(value):.4f}"
                for value in cost_matrix[index]
            ),
            f"{float(average[index]):.4f}",
            _ascii(rows[index]["job_name"]),
        ]
        for index in np.where(pareto_mask)[0]
    ]
    if table_rows:
        lines.extend(
            _table_lines(
                headers,
                table_rows,
                [True] * (len(headers) - 1) + [False],
            )
        )
    else:
        lines.append("(empty)")
    return "\n".join(lines)


__all__ = ["summarize_rows"]
