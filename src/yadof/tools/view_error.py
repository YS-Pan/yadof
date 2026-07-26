from __future__ import annotations

import colorsys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

from ..config import load_config
from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path
FAIL_RATE_COLOR = "darkblue"
PLOT_FIGSIZE = (5.5, 3.5)
PLOT_DPI = 600
PLOT_FONT_SIZE = 10
PLOT_TITLE_FONT_SIZE = 11
PLOT_TICK_FONT_SIZE = 8
PLOT_LEGEND_FONT_SIZE = 7
PLOT_LEGEND_FRAME_ALPHA = 0.6
PLOT_TIGHT_LAYOUT_PAD = 0.6
AXIS_LINE_WIDTH = 0.8
TREND_LINE_WIDTH = 2.0
GRID_LINE_WIDTH = 0.4
ERROR_MARKER_SIZE = 30.0


class ViewErrorError(RuntimeError):
    """Raised when recorded error data cannot be visualized."""


def _parse_dt(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def _metadata(record: Mapping[str, object]) -> dict[str, object]:
    metadata = record.get("job_metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _canonical_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status == "done":
        return "completed"
    return status or "unknown"


def _first_datetime(
    sources: Sequence[Mapping[str, object]], keys: Sequence[str]
) -> datetime | None:
    for key in keys:
        for source in sources:
            parsed = _parse_dt(source.get(key))
            if parsed is not None:
                return parsed
    return None


def _first_text(
    sources: Sequence[Mapping[str, object]], keys: Sequence[str]
) -> str | None:
    for key in keys:
        for source in sources:
            value = source.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return None


def _is_truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _error_type(
    record: Mapping[str, object],
    metadata: Mapping[str, object],
    status: str,
) -> str | None:
    if status == "completed":
        return None

    sources = (record, metadata)
    explicit = _first_text(sources, ("error_type", "failure_type"))
    if explicit is not None:
        return explicit
    if status == "timeout" or any(
        _is_truthy(source.get("timed_out")) for source in sources
    ):
        return "timeout"
    stage = _first_text(sources, ("failure_stage",))
    if stage is not None:
        return f"{stage} error"
    return status if status != "unknown" else "error"


def _error_message(
    record: Mapping[str, object], metadata: Mapping[str, object]
) -> str:
    message = _first_text(
        (record, metadata),
        (
            "error_message",
            "error",
            "rawdata_error",
            "rawdata_transfer_zip_error",
            "condor_hold_reason",
        ),
    )
    if message is None:
        return ""
    return " ".join(message.split())


def build_rows(
    workspace: WorkspaceLike,
    *,
    recorded_api=recorded_data_api,
) -> list[dict[str, object]]:
    """Build time-ordered evaluation rows with normalized error diagnostics."""

    list_records = getattr(recorded_api, "list_records", None)
    if list_records is None:
        raise ViewErrorError("recorded_data.api does not provide list_records()")

    rows: list[dict[str, object]] = []
    skipped_without_time = 0
    for row_number, raw_record in enumerate(list_records(workspace), start=1):
        if not isinstance(raw_record, Mapping):
            continue
        record = dict(raw_record)
        metadata = _metadata(record)
        status = _canonical_status(record.get("status") or metadata.get("status"))
        failed = status != "completed"
        event_time = _first_datetime(
            (record, metadata),
            (
                "failed_at",
                "ended_at",
                "runner_finished_at",
                "recorded_at",
                "started_at",
                "runner_started_at",
            ),
        )
        if event_time is None:
            skipped_without_time += 1
            continue
        rows.append(
            {
                "row_number": row_number,
                "job_name": str(
                    record.get("job_name")
                    or metadata.get("job_name")
                    or f"row_{row_number}"
                ),
                "status": status,
                "event_time": event_time,
                "failed": failed,
                "error_type": _error_type(record, metadata, status),
                "error_message": _error_message(record, metadata),
            }
        )

    rows.sort(
        key=lambda row: (row["event_time"], row["row_number"])  # type: ignore[index]
    )
    if not rows:
        suffix = (
            f"; skipped {skipped_without_time} records without a usable event time"
            if skipped_without_time
            else ""
        )
        raise ViewErrorError(
            f"No recorded evaluation rows found in recorded_data{suffix}."
        )
    return rows


def _table_lines(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    right_align: Sequence[bool],
) -> list[str]:
    widths = [len(text) for text in headers]
    for row in rows:
        for index, text in enumerate(row):
            widths[index] = max(widths[index], len(text))

    def fmt(row: Sequence[str]) -> str:
        return "  ".join(
            text.rjust(widths[index]) if right_align[index] else text.ljust(widths[index])
            for index, text in enumerate(row)
        )

    return [
        fmt(headers),
        "  ".join("-" * width for width in widths),
        *(fmt(row) for row in rows),
    ]


def summarize_rows(rows: Sequence[dict[str, object]]) -> str:
    failed_rows = [row for row in rows if row["failed"]]
    failure_rate = 100.0 * len(failed_rows) / len(rows)
    type_counts: dict[str, int] = {}
    for row in failed_rows:
        error_type = str(row["error_type"])
        type_counts[error_type] = type_counts.get(error_type, 0) + 1

    lines = [
        f"rows: {len(rows)}",
        f"errors: {len(failed_rows)}",
        f"failure rate: {failure_rate:.2f} %",
        f"time span: {rows[0]['event_time']} to {rows[-1]['event_time']}",
        "error type counts:",
    ]
    if type_counts:
        lines.extend(
            _table_lines(
                ("error type", "count"),
                tuple(
                    (error_type, str(count))
                    for error_type, count in sorted(type_counts.items())
                ),
                (False, True),
            )
        )
    else:
        lines.append("none")

    lines.append("error occurrences:")
    if failed_rows:
        lines.extend(
            _table_lines(
                ("time", "error type", "job", "message"),
                tuple(
                    (
                        row["event_time"].isoformat(sep=" "),  # type: ignore[union-attr]
                        str(row["error_type"]),
                        str(row["job_name"]),
                        str(row["error_message"]),
                    )
                    for row in failed_rows
                ),
                (False, False, False, False),
            )
        )
    else:
        lines.append("none")
    return "\n".join(lines)


def gaussian_kernel_smoother(x_data, y_data, fine_x, sigma):
    import numpy as np

    smoothed = np.zeros_like(fine_x, dtype=float)
    for index, fine_value in enumerate(fine_x):
        weights = np.exp(-((x_data - fine_value) ** 2) / (2 * sigma**2))
        weight_sum = float(np.sum(weights))
        if weight_sum > 0.0:
            smoothed[index] = np.sum(weights * y_data) / weight_sum
    return smoothed


def _time_cell_edges(rows: Sequence[dict[str, object]]) -> list[datetime]:
    times = [row["event_time"] for row in rows]
    if len(times) == 1:
        return [
            times[0] - timedelta(seconds=30),  # type: ignore[operator]
            times[0] + timedelta(seconds=30),  # type: ignore[operator]
        ]

    positive_gaps = [
        right - left  # type: ignore[operator]
        for left, right in zip(times, times[1:])
        if right > left
    ]
    fallback_half_gap = (
        min(positive_gaps) / 2 if positive_gaps else timedelta(seconds=30)
    )
    midpoints = [
        left + (right - left) / 2  # type: ignore[operator]
        for left, right in zip(times, times[1:])
    ]
    first_half_gap = (
        (times[1] - times[0]) / 2  # type: ignore[operator]
        if times[1] > times[0]
        else fallback_half_gap
    )
    last_half_gap = (
        (times[-1] - times[-2]) / 2  # type: ignore[operator]
        if times[-1] > times[-2]
        else fallback_half_gap
    )
    return [
        times[0] - first_half_gap,  # type: ignore[operator]
        *midpoints,
        times[-1] + last_half_gap,  # type: ignore[operator]
    ]


def _error_type_colors(error_types: Sequence[str]) -> dict[str, str]:
    unique = tuple(dict.fromkeys(str(value) for value in error_types))
    count = max(1, len(unique))
    colors: dict[str, str] = {}
    for index, error_type in enumerate(unique):
        red, green, blue = colorsys.hsv_to_rgb(index / count, 0.72, 0.78)
        colors[error_type] = "#{:02x}{:02x}{:02x}".format(
            round(red * 255),
            round(green * 255),
            round(blue * 255),
        )
    return colors


def _import_plot_modules():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise ViewErrorError(
            "matplotlib and numpy are required to render viewError PNG output"
        ) from exc
    return plt, np, mdates


def plot_rows(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    output_path: str | Path | None = None,
) -> Path:
    plt, np, mdates = _import_plot_modules()

    if output_path is None:
        output = (
            load_config(workspace).workspace.tool_output_dir
            / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
    else:
        output = Path(output_path).expanduser()
        if not output.is_absolute():
            output = load_config(workspace).workspace.tool_output_dir / output
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = PLOT_FONT_SIZE
    plt.rcParams["axes.linewidth"] = AXIS_LINE_WIDTH

    x_hours = np.asarray(
        [
            (row["event_time"] - rows[0]["event_time"]).total_seconds() / 3600.0  # type: ignore[operator]
            for row in rows
        ],
        dtype=float,
    )
    failures = np.asarray([row["failed"] for row in rows], dtype=float)
    if len(x_hours) == 1:
        fine_x = x_hours.copy()
        sigma = 1.0
    else:
        fine_x = np.linspace(float(np.min(x_hours)), float(np.max(x_hours)), 600)
        avg_spacing = float(np.mean(np.diff(x_hours)))
        sigma = max(
            1e-12,
            max(1, int(0.05 * len(rows))) * max(avg_spacing, 0.0) / 3.0,
        )
    fine_times = [
        rows[0]["event_time"] + timedelta(hours=float(value))  # type: ignore[operator]
        for value in fine_x
    ]
    local_failure = (
        gaussian_kernel_smoother(x_hours, failures, fine_x, sigma) * 100.0
    )
    global_failure = float(np.mean(failures) * 100.0)

    failed_rows = [row for row in rows if row["failed"]]
    error_types = tuple(
        dict.fromkeys(str(row["error_type"]) for row in failed_rows)
    )
    type_positions = {
        error_type: index for index, error_type in enumerate(error_types)
    }
    type_colors = _error_type_colors(error_types)

    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    for error_type in error_types:
        matching = [
            row for row in failed_rows if str(row["error_type"]) == error_type
        ]
        ax.scatter(
            [row["event_time"] for row in matching],
            [type_positions[error_type]] * len(matching),
            color=type_colors[error_type],
            edgecolors="white",
            linewidths=0.4,
            s=ERROR_MARKER_SIZE,
            label=error_type,
            zorder=3,
        )

    if error_types:
        ax.set_yticks(range(len(error_types)))
        ax.set_yticklabels(error_types)
        ax.set_ylim(-0.6, len(error_types) - 0.4)
    else:
        ax.set_yticks(())
        ax.set_ylim(-0.5, 0.5)
        ax.text(
            0.5,
            0.5,
            "No errors recorded",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=PLOT_FONT_SIZE,
            color="#555555",
        )

    ax2 = ax.twinx()
    ax2.plot(
        fine_times,
        local_failure,
        color=FAIL_RATE_COLOR,
        linewidth=TREND_LINE_WIDTH,
        alpha=0.6,
        label=f"avg. failure rate (global: {global_failure:.2f} %)",
    )
    ax2.set_ylabel("Failure rate (%)", fontsize=PLOT_FONT_SIZE)
    ax2.set_ylim(0.0, 100.0)
    ax2.tick_params(
        axis="both",
        labelsize=PLOT_TICK_FONT_SIZE,
        width=AXIS_LINE_WIDTH,
    )

    ax.set_xlabel("Time", fontsize=PLOT_FONT_SIZE)
    ax.set_ylabel("Error type", fontsize=PLOT_FONT_SIZE)
    ax.set_title("Errors from recorded_data", fontsize=PLOT_TITLE_FONT_SIZE)
    time_edges = _time_cell_edges(rows)
    ax.set_xlim(time_edges[0], time_edges[-1])
    ax.grid(
        True,
        axis="x",
        color="gainsboro",
        linestyle="-",
        linewidth=GRID_LINE_WIDTH,
        alpha=0.6,
    )
    ax.tick_params(
        axis="both",
        labelsize=PLOT_TICK_FONT_SIZE,
        width=AXIS_LINE_WIDTH,
    )

    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    if handles1 or handles2:
        ax.legend(
            [*handles1, *handles2],
            [*labels1, *labels2],
            loc="lower left",
            frameon=True,
            framealpha=PLOT_LEGEND_FRAME_ALPHA,
            fontsize=PLOT_LEGEND_FONT_SIZE,
            borderpad=0.3,
            labelspacing=0.3,
            handletextpad=0.5,
        )

    fig.tight_layout(pad=PLOT_TIGHT_LAYOUT_PAD)
    fig.savefig(output, dpi=PLOT_DPI)
    plt.close(fig)
    return output


def view_error(
    workspace: WorkspaceLike,
    *,
    output_path: str | Path | None = None,
) -> tuple[str, Path | None]:
    """Return an error summary and optionally render a PNG."""

    config = load_config(workspace)
    rows = build_rows(config.workspace)
    summary = summarize_rows(rows)
    output = (
        None
        if output_path is None
        else plot_rows(config.workspace, rows, output_path)
    )
    return summary, output


__all__ = [
    "ViewErrorError",
    "build_rows",
    "plot_rows",
    "summarize_rows",
    "view_error",
]
