from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence as SequenceABC
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..config import load_config
from ..job_template import api as job_template_api
from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path
MAX_VISIBLE_PARETO = 10
TREND_LINE_ALPHA = 0.25
TREND_LINE_WIDTH = 2.0
AVG_TREND_LINE_WIDTH = 4.0
HV_LINE_COLOR = "#0066CC"
HV_SHADE_ALPHA = 0.2
EVENT_LINE_ALPHA = TREND_LINE_ALPHA
EVENT_LINE_WIDTH = 1.2
EVENT_DASH_LENGTH = 4.0
OPT_LINE_STYLE = (0.0, (EVENT_DASH_LENGTH, EVENT_DASH_LENGTH))
HASH_LINE_STYLE = (EVENT_DASH_LENGTH, (EVENT_DASH_LENGTH, EVENT_DASH_LENGTH))
SCATTER_ALPHA = 0.6
MIN_SCATTER_ALPHA = 0.15
OPT_LINE_COLOR = "black"
HASH_LINE_COLOR = "#FFAA00"
OPT_LINE_LABEL = "Opt. start"
HASH_LINE_LABEL = "Hash change"
EVENT_LINE_LABELS = (OPT_LINE_LABEL, HASH_LINE_LABEL)
PLOT_COLORS = ["#FF0000", "#FFAA00", "#58A500", "#00BFE9", "#2000AA", "#960096", "#808080"]
PLOT_MARKERS = ["o", "s", "D", "^", "v", "<", ">"]
PLOT_FIGSIZE = (5.5, 3.5)
PLOT_DPI = 600
PLOT_FONT_SIZE = 10
PLOT_TITLE_FONT_SIZE = 11
PLOT_TICK_FONT_SIZE = 8
PLOT_LEGEND_FONT_SIZE = 7
PLOT_LEGEND_FRAME_ALPHA = 0.6
PLOT_LEGEND_EDGE_PAD = 0.015
PLOT_LEGEND_GAP = 0.01
PLOT_GENERATION_FONT_SIZE = 8
PLOT_TIGHT_LAYOUT_PAD = 0.6
AXIS_LINE_WIDTH = 0.8
GRID_LINE_WIDTH = 0.4
SCATTER_MARKER_SIZE = 3.0
SCATTER_EDGE_LINE_WIDTH = 0.4
PARETO_MARKER_AREA = 60.0
PARETO_EDGE_LINE_WIDTH = 0.75
GENERATION_SHADE_COLOR = "black"
GENERATION_SHADE_ALPHA = 0.1
GENERATION_LABEL_Y = 0.98
MAX_REPORTED_ISSUES = 10


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


def _record_issue(issues: list[str] | None, message: str) -> None:
    if issues is not None:
        issues.append(message)


def _metadata_by_job(
    workspace: WorkspaceLike,
    recorded_api=recorded_data_api,
    *,
    issues: list[str] | None = None,
) -> dict[str, dict[str, object]]:
    list_records = getattr(recorded_api, "list_records", None)
    if list_records is None:
        return {}
    out: dict[str, dict[str, object]] = {}
    try:
        for record in list_records(workspace):
            if not isinstance(record, dict) or "job_name" not in record:
                continue
            metadata = record.get("job_metadata")
            row = dict(metadata) if isinstance(metadata, dict) else {}
            for key in ("run_id", "optimization_index", "generation_index", "population_index"):
                if key in record:
                    row[key] = record[key]
            out[str(record["job_name"])] = row
    except Exception as exc:  # noqa: BLE001 - annotations must not block cost data.
        _record_issue(
            issues,
            f"individual metadata annotations were ignored: {exc}",
        )
    return out


def _opt_metadata_by_job(
    workspace: WorkspaceLike,
    recorded_api=recorded_data_api,
    *,
    issues: list[str] | None = None,
) -> dict[str, dict[str, object]]:
    list_optimization_metadata = getattr(recorded_api, "list_optimization_metadata", None)
    if list_optimization_metadata is None:
        return {}

    out: dict[str, dict[str, object]] = {}
    run_order: dict[str, int] = {}
    try:
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
    except Exception as exc:  # noqa: BLE001 - annotations must not block cost data.
        _record_issue(
            issues,
            f"optimization metadata annotations were ignored: {exc}",
        )
    return out


def _metadata_int(metadata: dict[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
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
    issues: list[str] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, object]]:
    """Build display rows from recorded_data using dynamic cost calculation."""

    get_history = getattr(recorded_api, "get_historical_results", None)
    if get_history is None:
        raise ViewCostError("recorded_data.api does not provide get_historical_results()")

    try:
        history = get_history(
            workspace,
            status=status,
            **({"progress": progress} if progress is not None else {}),
        )
    except ViewCostError:
        raise
    except Exception as exc:  # noqa: BLE001 - keep the CLI from printing raw internals.
        raise ViewCostError(f"Could not read recorded_data history: {exc}") from exc

    candidates: list[dict[str, object]] = []
    history_row_count = 0
    for row_number, item in enumerate(history, start=1):
        history_row_count += 1
        try:
            job_name_raw, variables_raw, costs_raw = item
        except (TypeError, ValueError):
            _record_issue(
                issues,
                f"history row {row_number} was skipped: unexpected row shape",
            )
            continue
        job_name = str(job_name_raw)
        try:
            variables = _as_float_tuple(
                variables_raw, field_name="variables", job_name=job_name
            )
            costs = _as_float_tuple(
                costs_raw, field_name="costs", job_name=job_name
            )
        except ViewCostError as exc:
            _record_issue(issues, f"history row {row_number} was skipped: {exc}")
            continue
        if not costs:
            _record_issue(
                issues,
                f"history row {row_number} for job {job_name!r} was skipped: costs are empty",
            )
            continue
        try:
            average_cost = math.fsum(costs) / len(costs)
        except OverflowError:
            average_cost = math.inf
        if not math.isfinite(average_cost):
            _record_issue(
                issues,
                f"history row {row_number} for job {job_name!r} was skipped: average cost is non-finite",
            )
            continue
        candidates.append(
            {
                "row_number": row_number,
                "job_name": job_name,
                "variables": variables,
                "costs": costs,
                "average_cost": average_cost,
            }
        )

    status_text = "all statuses" if status is None else f"status={status!r}"
    if not candidates:
        if history_row_count:
            detail = ""
            if issues:
                detail = f" First issue: {issues[0]}"
            raise ViewCostError(
                f"No plottable historical results found in recorded_data ({status_text}).{detail}"
            )
        raise ViewCostError(
            f"No completed historical results found in recorded_data ({status_text})."
        )

    width_counts = Counter(len(row["costs"]) for row in candidates)  # type: ignore[arg-type]
    objective_count = width_counts.most_common(1)[0][0]
    metadata = _metadata_by_job(workspace, recorded_api, issues=issues)
    opt_metadata = _opt_metadata_by_job(workspace, recorded_api, issues=issues)
    rows: list[dict[str, object]] = []
    for row in candidates:
        costs = row["costs"]
        if len(costs) != objective_count:  # type: ignore[arg-type]
            _record_issue(
                issues,
                f"history row {row['row_number']} for job {row['job_name']!r} was skipped: "
                f"expected {objective_count} objectives, got {len(costs)}",  # type: ignore[arg-type]
            )
            continue

        job_name = str(row["job_name"])
        job_metadata = metadata.get(job_name, {})
        job_opt_metadata = opt_metadata.get(job_name, {})
        optimization_index = _metadata_int(job_metadata, "optimization_index")
        if optimization_index is None:
            optimization_index = job_opt_metadata.get("optimization_index")
        generation_index = _metadata_int(job_metadata, "generation_index")
        if generation_index is None:
            generation_index = job_opt_metadata.get("generation_index")
        optimization_run_id = _metadata_str(job_metadata, "run_id") or job_opt_metadata.get("optimization_run_id")
        row.update(
            {
                "optimization_index": optimization_index,
                "optimization_run_id": optimization_run_id,
                "generation_index": generation_index,
                "job_static_hash": _metadata_str(job_metadata, "job_static_hash"),
            }
        )
        rows.append(row)
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
        try:
            names = [str(name) for name in get_names(workspace)]
            if len(names) == objective_count:
                return names
        except Exception:  # noqa: BLE001 - generic labels keep the plot usable.
            pass
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


def _visible_pareto_mask(pareto_mask, display_values):
    import numpy as np

    if int(np.sum(pareto_mask)) <= MAX_VISIBLE_PARETO:
        return pareto_mask
    out = np.zeros_like(pareto_mask)
    keep = np.where(pareto_mask)[0][
        np.argsort(display_values[pareto_mask])[:MAX_VISIBLE_PARETO]
    ]
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


def _row_cell_edges(rows: Sequence[dict[str, object]]) -> list[float]:
    x = [float(row["row_number"]) for row in rows]
    if len(x) == 1:
        return [x[0] - 0.5, x[0] + 0.5]

    midpoints = [(left + right) / 2.0 for left, right in zip(x, x[1:])]
    return [
        x[0] - (midpoints[0] - x[0]),
        *midpoints,
        x[-1] + (x[-1] - midpoints[-1]),
    ]


def _generation_groups(
    rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    active_key: tuple[object, int] | None = None

    for index, row in enumerate(rows):
        generation = _metadata_int(row, "generation_index")
        run_identity = row.get("optimization_run_id")
        if run_identity is None:
            run_identity = row.get("optimization_index")
        key = None if generation is None else (run_identity, generation)

        if key == active_key:
            if key is not None:
                groups[-1]["last_position"] = index
                groups[-1]["last_x"] = float(row["row_number"])
                groups[-1]["rows"].append(row)  # type: ignore[union-attr]
            continue
        active_key = key
        if key is None:
            continue
        groups.append(
            {
                "generation_index": generation,
                "first_position": index,
                "last_position": index,
                "first_x": float(row["row_number"]),
                "last_x": float(row["row_number"]),
                "rows": [row],
            }
        )
    return groups


def _generation_regions(
    rows: Sequence[dict[str, object]],
) -> list[tuple[int, float, float]]:
    edges = _row_cell_edges(rows)
    regions: list[tuple[int, float, float]] = []
    for group in _generation_groups(rows):
        first_position = int(group["first_position"])
        last_position = int(group["last_position"])
        regions.append(
            (
                int(group["generation_index"]),
                edges[first_position],
                edges[last_position + 1],
            )
        )
    return regions


def _draw_generation_regions(
    ax, regions: Sequence[tuple[int, float, float]]
) -> None:
    xaxis_transform = ax.get_xaxis_transform()
    for generation, left, right in regions:
        if generation % 2:
            ax.axvspan(
                left,
                right,
                facecolor=GENERATION_SHADE_COLOR,
                edgecolor="none",
                alpha=GENERATION_SHADE_ALPHA,
                zorder=0,
            )
        ax.text(
            (left + right) / 2.0,
            GENERATION_LABEL_Y,
            str(generation),
            transform=xaxis_transform,
            ha="center",
            va="top",
            color="black",
            fontsize=PLOT_GENERATION_FONT_SIZE,
            zorder=4,
        )


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


def hypervolume_series(
    rows: Sequence[dict[str, object]],
    *,
    reference_point: Sequence[float] | None = None,
):
    """Return all-individual and current-generation HV at generation endpoints."""

    try:
        import numpy as np
        from pymoo.indicators.hv import HV
    except ImportError as exc:
        raise ViewCostError(
            "numpy and pymoo are required to calculate hypervolume"
        ) from exc

    if not rows:
        raise ViewCostError("Cannot calculate hypervolume from empty rows")

    groups = _generation_groups(rows)
    if not groups:
        groups = [
            {
                "last_x": float(rows[-1]["row_number"]),
                "rows": list(rows),
            }
        ]

    all_costs = np.asarray([row["costs"] for row in rows], dtype=float)
    objective_count = int(all_costs.shape[1])
    if reference_point is None:
        reference = (1.0,) * objective_count
    else:
        reference = tuple(float(value) for value in reference_point)
        if len(reference) != objective_count:
            raise ViewCostError(
                f"hypervolume reference point has {len(reference)} values; "
                f"expected {objective_count}"
            )
        if not all(math.isfinite(value) for value in reference):
            raise ViewCostError(
                "hypervolume reference point contains non-finite values"
            )

    indicator = HV(ref_point=np.asarray(reference, dtype=float))
    cumulative_rows: list[dict[str, object]] = []
    x_values: list[float] = []
    all_values: list[float] = []
    generation_values: list[float] = []

    def calculate(group_rows: Sequence[dict[str, object]]) -> float:
        matrix = np.asarray([row["costs"] for row in group_rows], dtype=float)
        valid = matrix[np.all((matrix >= 0.0) & (matrix <= 1.0), axis=1)]
        return float(indicator.do(valid)) if len(valid) else 0.0

    for group in groups:
        generation_rows = group["rows"]
        cumulative_rows.extend(generation_rows)  # type: ignore[arg-type]
        x_values.append(float(group["last_x"]))
        generation_values.append(calculate(generation_rows))  # type: ignore[arg-type]
        all_values.append(calculate(cumulative_rows))

    return (
        np.asarray(x_values, dtype=float),
        np.asarray(all_values, dtype=float),
        np.asarray(generation_values, dtype=float),
        reference,
    )


def _hypervolume_axis_ylim(*series) -> tuple[float, float]:
    import numpy as np

    values = np.concatenate([np.asarray(item, dtype=float) for item in series])
    finite = values[np.isfinite(values)]
    if len(finite) == 0 or float(np.max(finite)) <= 0.0:
        return 0.0, 1.0
    return 0.0, float(np.max(finite)) * 1.05


def _add_split_legends(ax, axes: Sequence[object]) -> None:
    data_legend: dict[str, object] = {}
    event_legend: dict[str, object] = {}
    for source_axis in axes:
        handles, labels = source_axis.get_legend_handles_labels()
        for handle, label in zip(handles, labels):
            target = event_legend if label in EVENT_LINE_LABELS else data_legend
            target.setdefault(label, handle)

    data_artist = None
    if data_legend:
        data_artist = ax.legend(
            list(data_legend.values()),
            list(data_legend.keys()),
            loc="lower left",
            bbox_to_anchor=(PLOT_LEGEND_EDGE_PAD, PLOT_LEGEND_EDGE_PAD),
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
            ax.figure.canvas.draw()
            renderer = ax.figure.canvas.get_renderer()
            data_bbox = data_artist.get_window_extent(renderer).transformed(
                ax.transAxes.inverted()
            )
            event_x = data_bbox.x1 + PLOT_LEGEND_GAP
        ax.legend(
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
            ax.add_artist(data_artist)


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
    issues: Sequence[str] = (),
) -> str:
    import numpy as np

    names = objective_names(workspace, rows, objective_api)
    cost_matrix = np.asarray([row["costs"] for row in rows], dtype=float)
    average = np.asarray([row["average_cost"] for row in rows], dtype=float)
    raw_pareto = is_pareto_efficient(cost_matrix)
    pareto_mask = _visible_pareto_mask(raw_pareto, average)
    if int(np.sum(pareto_mask)) > max_pareto:
        pareto_mask = _visible_pareto_mask(raw_pareto, average)

    lines = [
        f"rows: {len(rows)}",
        f"objectives: {_ascii(', '.join(names))}",
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
        f"Pareto front shown: {int(np.sum(pareto_mask))} of {int(np.sum(raw_pareto))}",
        "Pareto front:",
    ]
    headers = ["row", *[_ascii(name) for name in names], "avg. cost", "job_name"]
    table_rows = [
        [
            str(int(rows[idx]["row_number"])),
            *(f"{float(value):.4f}" for value in cost_matrix[idx]),
            f"{float(average[idx]):.4f}",
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
    average = np.asarray([row["average_cost"] for row in rows], dtype=float)
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
        else max(1.0, SCATTER_MARKER_SIZE * math.sqrt(threshold / len(rows)))
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
                linewidths=PARETO_EDGE_LINE_WIDTH,
                s=fixed_markersize_pareto,
                zorder=3,
            )

    if len(x) == 1:
        fine_x = x.copy()
        local_avg = average.copy()
    else:
        fine_x = np.linspace(float(np.min(x)), float(np.max(x)), 600)
        avg_spacing = float(np.mean(np.diff(x)))
        sigma = max(1e-12, max(1, int(0.03 * len(x))) * avg_spacing / 3.0)
        local_avg = gaussian_kernel_smoother(x, average, fine_x, sigma)

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
            s=(math.sqrt(fixed_markersize_pareto) * border_size_multiplier) ** 2,
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
        step="post",
        facecolor=HV_LINE_COLOR,
        edgecolor="none",
        alpha=HV_SHADE_ALPHA,
        zorder=0.8,
    )
    ax2.step(
        hv_x,
        all_hv,
        where="post",
        color=HV_LINE_COLOR,
        linewidth=TREND_LINE_WIDTH,
        alpha=0.7,
        label="HV (all individuals)",
        zorder=1,
    )
    ax2.step(
        hv_x,
        generation_hv,
        where="post",
        color=HV_LINE_COLOR,
        linewidth=TREND_LINE_WIDTH,
        alpha=0.7,
        linestyle="--",
        label="HV (current generation)",
        zorder=1,
    )
    ax2.set_ylabel("Hypervolume (HV)", color=HV_LINE_COLOR, fontsize=PLOT_FONT_SIZE)
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


def view_cost(
    workspace: WorkspaceLike,
    *,
    status: str | None = "completed",
    output_path: str | Path | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[str, Path | None]:
    """Return a dynamic-cost summary and optionally render a PNG."""

    config = load_config(workspace)
    issues: list[str] = []
    rows = build_rows(
        config.workspace,
        status=status,
        issues=issues,
        progress=progress,
    )
    summary = summarize_rows(config.workspace, rows, issues=issues)
    output = (
        None
        if output_path is None
        else plot_rows(config.workspace, rows, output_path)
    )
    return summary, output


__all__ = [
    "ViewCostError",
    "build_rows",
    "hypervolume_series",
    "objective_names",
    "plot_rows",
    "summarize_rows",
    "view_cost",
]
