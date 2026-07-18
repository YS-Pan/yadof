from __future__ import annotations

import math
from collections.abc import Sequence as SequenceABC
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from ..config import load_config
from ..job_template import api as job_template_api
from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path
MAX_VISIBLE_PARETO = 10
TREND_LINE_ALPHA = 0.25
TREND_LINE_WIDTH = 6.0
SCATTER_ALPHA = 0.6
MIN_SCATTER_ALPHA = 0.15
OPT_LINE_COLOR = "black"
HASH_LINE_COLOR = "#FFAA00"
PLOT_COLORS = ["#FF0000", "#FFAA00", "#58A500", "#00BFE9", "#2000AA", "#960096", "#808080"]
PLOT_MARKERS = ["o", "s", "D", "^", "v", "<", ">"]
PLOT_FONT_SIZE = 14
PLOT_LEGEND_FONT_SIZE = 12


class ViewCostError(RuntimeError):
    """Raised when historical cost data cannot be visualized."""


def _ascii(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _as_float_tuple(values: Sequence[object], *, field_name: str, job_name: str) -> tuple[float, ...]:
    try:
        out = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ViewCostError(f"{field_name} for job {job_name!r} is not numeric") from exc
    if not all(math.isfinite(value) for value in out):
        raise ViewCostError(f"{field_name} for job {job_name!r} contains non-finite values")
    return out


def _metadata_by_job(
    workspace: WorkspaceLike, recorded_api=recorded_data_api
) -> dict[str, dict[str, object]]:
    list_records = getattr(recorded_api, "list_records", None)
    if list_records is None:
        return {}
    out: dict[str, dict[str, object]] = {}
    for record in list_records(workspace):
        if not isinstance(record, dict) or "job_name" not in record:
            continue
        metadata = record.get("job_metadata")
        row = dict(metadata) if isinstance(metadata, dict) else {}
        for key in ("run_id", "optimization_index", "generation_index", "population_index"):
            if key in record:
                row[key] = record[key]
        out[str(record["job_name"])] = row
    return out


def _opt_metadata_by_job(
    workspace: WorkspaceLike, recorded_api=recorded_data_api
) -> dict[str, dict[str, object]]:
    list_optimization_metadata = getattr(recorded_api, "list_optimization_metadata", None)
    if list_optimization_metadata is None:
        return {}

    out: dict[str, dict[str, object]] = {}
    run_order: dict[str, int] = {}
    for row_number, raw_row in enumerate(
        list_optimization_metadata(workspace), start=1
    ):
        if not isinstance(raw_row, Mapping):
            continue
        row = dict(raw_row)
        run_id = str(row.get("run_id") or row.get("optimization_index") or f"run_{row_number}")
        if run_id not in run_order:
            run_order[run_id] = len(run_order) + 1
        created_job_names = row.get("created_job_names", ())
        if isinstance(created_job_names, (str, bytes)) or not isinstance(created_job_names, SequenceABC):
            created_job_names = (created_job_names,)
        for job_name_raw in created_job_names:
            if job_name_raw in (None, ""):
                continue
            out[str(job_name_raw)] = {
                "optimization_index": run_order[run_id],
                "optimization_run_id": run_id,
                "generation_index": _metadata_int(row, "generation_index"),
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "source": row.get("source"),
                "surrogate_used": row.get("surrogate_used"),
            }
    return out


def _metadata_int(metadata: dict[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value in (None, ""):
        return None
    return str(value)


def build_rows(
    workspace: WorkspaceLike,
    *,
    status: str | None = "completed",
    recorded_api=recorded_data_api,
) -> list[dict[str, object]]:
    """Build display rows from recorded_data using dynamic cost calculation."""

    get_history = getattr(recorded_api, "get_historical_results", None)
    if get_history is None:
        raise ViewCostError("recorded_data.api does not provide get_historical_results()")

    try:
        history = get_history(workspace, status=status)
    except ViewCostError:
        raise
    except Exception as exc:  # noqa: BLE001 - keep the CLI from printing raw internals.
        raise ViewCostError(f"Could not read recorded_data history: {exc}") from exc

    metadata = _metadata_by_job(workspace, recorded_api)
    opt_metadata = _opt_metadata_by_job(workspace, recorded_api)
    rows: list[dict[str, object]] = []
    objective_count: int | None = None
    for row_number, item in enumerate(history, start=1):
        if len(item) != 3:
            raise ViewCostError("recorded_data.get_historical_results() returned an unexpected row shape")
        job_name_raw, variables_raw, costs_raw = item
        job_name = str(job_name_raw)
        variables = _as_float_tuple(variables_raw, field_name="variables", job_name=job_name)
        costs = _as_float_tuple(costs_raw, field_name="costs", job_name=job_name)
        if not costs:
            continue
        if objective_count is None:
            objective_count = len(costs)
        elif len(costs) != objective_count:
            raise ViewCostError("Historical rows have inconsistent objective counts")

        job_metadata = metadata.get(job_name, {})
        job_opt_metadata = opt_metadata.get(job_name, {})
        optimization_index = _metadata_int(job_metadata, "optimization_index")
        if optimization_index is None:
            optimization_index = job_opt_metadata.get("optimization_index")
        generation_index = _metadata_int(job_metadata, "generation_index")
        if generation_index is None:
            generation_index = job_opt_metadata.get("generation_index")
        optimization_run_id = _metadata_str(job_metadata, "run_id") or job_opt_metadata.get("optimization_run_id")
        rows.append(
            {
                "row_number": row_number,
                "job_name": job_name,
                "variables": variables,
                "costs": costs,
                "optimization_index": optimization_index,
                "optimization_run_id": optimization_run_id,
                "generation_index": generation_index,
                "job_static_hash": _metadata_str(job_metadata, "job_static_hash"),
            }
        )

    if not rows:
        status_text = "all statuses" if status is None else f"status={status!r}"
        raise ViewCostError(f"No completed historical results found in recorded_data ({status_text}).")
    return rows


def objective_names(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    objective_api=job_template_api,
) -> list[str]:
    first_costs = rows[0]["costs"]
    objective_count = len(first_costs)  # type: ignore[arg-type]
    get_names = getattr(objective_api, "get_objective_names", None)
    if callable(get_names):
        names = [str(name) for name in get_names(workspace)]
        if len(names) == objective_count:
            return names
    return [f"objective_{idx + 1}" for idx in range(objective_count)]


def is_pareto_efficient(costs) -> object:
    import numpy as np

    efficient = np.ones(costs.shape[0], dtype=bool)
    for i, c in enumerate(costs):
        if efficient[i]:
            efficient[efficient] = np.any(costs[efficient] < c, axis=1)
            efficient[i] = True
    return efficient


def gaussian_kernel_smoother(x_data, y_data, fine_x, sigma):
    import numpy as np

    smoothed = np.zeros_like(fine_x, dtype=float)
    for i, fx in enumerate(fine_x):
        weights = np.exp(-((x_data - fx) ** 2) / (2 * sigma**2))
        weight_sum = float(np.sum(weights))
        if weight_sum > 0.0:
            smoothed[i] = np.sum(weights * y_data) / weight_sum
    return smoothed


def _visible_pareto_mask(pareto_mask, combined):
    import numpy as np

    if int(np.sum(pareto_mask)) <= MAX_VISIBLE_PARETO:
        return pareto_mask
    out = np.zeros_like(pareto_mask)
    keep = np.where(pareto_mask)[0][np.argsort(combined[pareto_mask])[:MAX_VISIBLE_PARETO]]
    out[keep] = True
    return out


def _optimization_start_rows(rows: Sequence[dict[str, object]]) -> list[tuple[int, float]]:
    starts: list[tuple[int, float]] = []
    seen: set[int] = set()
    for row in rows:
        opt_idx = row.get("optimization_index")
        if opt_idx is None or opt_idx in seen:
            continue
        seen.add(int(opt_idx))
        starts.append((int(opt_idx), float(row["row_number"])))
    return starts


def _hash_change_rows(rows: Sequence[dict[str, object]]) -> list[float]:
    starts: list[float] = []
    previous_hash = None
    seen_hash = False
    for row in rows:
        current_hash = row.get("job_static_hash")
        if current_hash is None:
            continue
        if seen_hash and current_hash != previous_hash:
            starts.append(float(row["row_number"]))
        previous_hash, seen_hash = current_hash, True
    return starts


def _scatter_alpha(row_count: int, *, threshold: int = 1000) -> float:
    row_count = max(1, int(row_count))
    if row_count <= threshold:
        return SCATTER_ALPHA
    return max(MIN_SCATTER_ALPHA, SCATTER_ALPHA * math.sqrt(float(threshold) / float(row_count)))


def _combined_axis_ylim(combined, left_ylim: tuple[float, float]) -> tuple[float, float]:
    import numpy as np

    combined_values = np.asarray(combined, dtype=float)
    combined_min = min(0.0, float(np.min(combined_values)) * 1.05)
    combined_max = max(0.0, float(np.max(combined_values)))
    left_min, left_max = (float(left_ylim[0]), float(left_ylim[1]))
    if not math.isfinite(left_min) or not math.isfinite(left_max) or left_max <= left_min:
        return combined_min, max(combined_max * 1.05, 1.0)

    one_position = (1.0 - left_min) / (left_max - left_min)
    if one_position <= 0.0:
        return combined_min, max(combined_max * 1.05, 1.0)
    if one_position >= 1.0:
        return combined_min, max(combined_max, combined_min + 1e-12)

    axis_max = combined_min + (combined_max - combined_min) / one_position
    return combined_min, max(axis_max, combined_max, combined_min + 1e-12)


def _table_lines(headers: Sequence[str], rows: Sequence[Sequence[str]], right_align: Sequence[bool]) -> list[str]:
    widths = [len(text) for text in headers]
    for row in rows:
        for idx, text in enumerate(row):
            widths[idx] = max(widths[idx], len(text))

    def fmt(row: Sequence[str]) -> str:
        return "  ".join(
            text.rjust(widths[idx]) if right_align[idx] else text.ljust(widths[idx])
            for idx, text in enumerate(row)
        )

    return [fmt(headers), "  ".join("-" * width for width in widths), *(fmt(row) for row in rows)]


def summarize_rows(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    *,
    max_pareto: int = MAX_VISIBLE_PARETO,
    objective_api=job_template_api,
) -> str:
    import numpy as np

    names = objective_names(workspace, rows, objective_api)
    cost_matrix = np.asarray([row["costs"] for row in rows], dtype=float)
    combined = np.sum(cost_matrix, axis=1)
    raw_pareto = is_pareto_efficient(cost_matrix)
    pareto_mask = _visible_pareto_mask(raw_pareto, combined)
    if int(np.sum(pareto_mask)) > max_pareto:
        pareto_mask = _visible_pareto_mask(raw_pareto, combined)

    lines = [
        f"rows: {len(rows)}",
        f"objectives: {_ascii(', '.join(names))}",
        f"Pareto front shown: {int(np.sum(pareto_mask))} of {int(np.sum(raw_pareto))}",
        "Pareto front:",
    ]
    headers = ["row", *[_ascii(name) for name in names], "combined", "job_name"]
    table_rows = [
        [
            str(int(rows[idx]["row_number"])),
            *(f"{float(value):.4f}" for value in cost_matrix[idx]),
            f"{float(combined[idx]):.4f}",
            _ascii(rows[idx]["job_name"]),
        ]
        for idx in np.where(pareto_mask)[0]
    ]
    if table_rows:
        lines.extend(_table_lines(headers, table_rows, [True] * (len(headers) - 1) + [False]))
    else:
        lines.append("(empty)")
    return "\n".join(lines)


def _import_plot_modules():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        import numpy as np
        from cycler import cycler
    except ImportError as exc:
        raise ViewCostError("matplotlib and cycler are required to render viewCost PNG output") from exc
    return plt, np, cycler


def plot_rows(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    output_path: str | Path | None = None,
    *,
    objective_api=job_template_api,
) -> Path:
    plt, np, cycler = _import_plot_modules()

    if output_path is None:
        output = (
            load_config(workspace).workspace.tool_output_dir
            / f"cost_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
    else:
        output = Path(output_path).expanduser()
        if not output.is_absolute():
            output = load_config(workspace).workspace.tool_output_dir / output
    output.parent.mkdir(parents=True, exist_ok=True)

    names = objective_names(workspace, rows, objective_api)
    x = np.asarray([row["row_number"] for row in rows], dtype=float)
    cost_matrix = np.asarray([row["costs"] for row in rows], dtype=float)
    combined = np.sum(cost_matrix, axis=1)
    raw_pareto = is_pareto_efficient(cost_matrix)
    pareto_mask = _visible_pareto_mask(raw_pareto, combined)
    optimization_start_rows = _optimization_start_rows(rows)
    hash_change_rows = _hash_change_rows(rows)

    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = PLOT_FONT_SIZE
    plt.rcParams["axes.prop_cycle"] = cycler("color", PLOT_COLORS)

    threshold = 1000
    markersize = 6.0 if len(rows) <= threshold else max(1.0, 6.0 * math.sqrt(threshold / len(rows)))
    alpha = _scatter_alpha(len(rows), threshold=threshold)

    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax1.set_axisbelow(True)
    fixed_markersize_pareto = 200.0
    border_size_multiplier = 1.5
    line_style = {"linewidth": TREND_LINE_WIDTH, "alpha": TREND_LINE_ALPHA, "linestyle": "-", "zorder": 0.5}

    first_opt = True
    for _, start_x in optimization_start_rows:
        ax1.axvline(start_x, color=OPT_LINE_COLOR, label="Optimization start" if first_opt else None, **line_style)
        first_opt = False

    first_hash = True
    for start_x in hash_change_rows:
        ax1.axvline(start_x, color=HASH_LINE_COLOR, label="Static input hash change" if first_hash else None, **line_style)
        first_hash = False

    for idx, name in enumerate(names):
        color = PLOT_COLORS[idx % len(PLOT_COLORS)]
        marker = PLOT_MARKERS[idx % len(PLOT_MARKERS)]
        y = cost_matrix[:, idx]
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
                s=(math.sqrt(fixed_markersize_pareto) * border_size_multiplier) ** 2,
                zorder=2,
            )
            ax1.scatter(
                x[pareto_mask],
                y[pareto_mask],
                label=name,
                marker=marker,
                edgecolors=color,
                facecolors="none",
                linewidths=1.5,
                s=fixed_markersize_pareto,
                zorder=3,
            )

    ax1.set_xlabel("Evaluation index")
    ax1.set_ylabel("Individual costs")
    ax1.set_xlim((x[0] - 0.5, x[0] + 0.5) if len(x) == 1 else (float(np.min(x)), float(np.max(x))))
    y_max = max(1.0, float(np.max(cost_matrix)) * 1.05)
    y_min = min(0.0, float(np.min(cost_matrix)) * 1.05)
    ax1.set_ylim(y_min, y_max)
    ax1.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.7)

    ax2 = ax1.twinx()
    if len(x) == 1:
        fine_x = x.copy()
        local_avg = combined.copy()
    else:
        fine_x = np.linspace(float(np.min(x)), float(np.max(x)), 600)
        avg_spacing = float(np.mean(np.diff(x)))
        sigma = max(1e-12, max(1, int(0.03 * len(x))) * avg_spacing / 3.0)
        local_avg = gaussian_kernel_smoother(x, combined, fine_x, sigma)

    ax2.plot(
        fine_x,
        local_avg,
        color="black",
        linewidth=TREND_LINE_WIDTH,
        alpha=TREND_LINE_ALPHA,
        linestyle="-",
        marker=None,
        zorder=1,
    )
    ax2.scatter(
        x[~pareto_mask],
        combined[~pareto_mask],
        color="black",
        label=None if np.any(pareto_mask) else "Combined cost",
        marker="o",
        alpha=alpha,
        s=markersize**2,
    )
    if np.any(pareto_mask):
        ax2.scatter(
            x[pareto_mask],
            combined[pareto_mask],
            facecolors="white",
            edgecolors="white",
            linewidths=0,
            marker="o",
            s=(math.sqrt(fixed_markersize_pareto) * border_size_multiplier) ** 2,
            zorder=2,
        )
        ax2.scatter(
            x[pareto_mask],
            combined[pareto_mask],
            label="Combined cost",
            facecolors="none",
            edgecolors="black",
            linewidths=1.5,
            marker="o",
            s=fixed_markersize_pareto,
            zorder=3,
        )

    ax2.set_ylabel("Combined cost")
    ax2.set_ylim(*_combined_axis_ylim(combined, ax1.get_ylim()))

    legend = {}
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    for handle, label in list(zip(handles1, labels1)) + list(zip(handles2, labels2)):
        legend.setdefault(label, handle)
    ax1.legend(
        list(legend.values()),
        list(legend.keys()),
        loc="lower left",
        frameon=True,
        fontsize=PLOT_LEGEND_FONT_SIZE,
    )
    ax1.set_title("Optimization costs from recorded_data")

    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)
    return output


def view_cost(
    workspace: WorkspaceLike,
    *,
    status: str | None = "completed",
    output_path: str | Path | None = None,
) -> tuple[str, Path | None]:
    """Return a dynamic-cost summary and optionally render a PNG."""

    config = load_config(workspace)
    rows = build_rows(config.workspace, status=status)
    summary = summarize_rows(config.workspace, rows)
    output = (
        None
        if output_path is None
        else plot_rows(config.workspace, rows, output_path)
    )
    return summary, output


__all__ = [
    "ViewCostError",
    "build_rows",
    "objective_names",
    "plot_rows",
    "summarize_rows",
    "view_cost",
]
