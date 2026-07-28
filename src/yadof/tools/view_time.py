from __future__ import annotations

import colorsys
import math
from collections.abc import Sequence as SequenceABC
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

from ..config import load_config
from ..evaluate_manager.condor_runner import (
    condor_timeout_execution_site_from_text,
)
from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path
FAIL_RATE_COLOR = "darkblue"
FAIL_RATE_LINE_ALPHA = 0.1
HASH_LINE_COLOR = "#FFAA00"
OPT_LINE_COLOR = "black"
OPT_LINE_LABEL = "Opt. start"
HASH_LINE_LABEL = "Hash change"
EVENT_LINE_LABELS = (OPT_LINE_LABEL, HASH_LINE_LABEL)
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
TREND_LINE_WIDTH = 2.0
TREND_LINE_ALPHA = 0.25
EVENT_LINE_ALPHA = 0.25
EVENT_LINE_WIDTH = 1.2
EVENT_DASH_LENGTH = 4.0
OPT_LINE_STYLE = (0.0, (EVENT_DASH_LENGTH, EVENT_DASH_LENGTH))
HASH_LINE_STYLE = (EVENT_DASH_LENGTH, (EVENT_DASH_LENGTH, EVENT_DASH_LENGTH))
GRID_LINE_WIDTH = 0.4
SCATTER_MARKER_SIZE = 3.0
SCATTER_EDGE_LINE_WIDTH = 0.4
ERROR_SCATTER_MARKER_SIZE = 5.0
ERROR_RING_LINE_WIDTH = 1.0
ERROR_BAND_BOTTOM = 0.80
ERROR_BAND_TOP = 0.90
ELAPSED_DATA_TOP = 0.72
ERROR_BAND_LINE_WIDTH = 0.6
ERROR_LABEL_X = 0.015
GENERATION_SHADE_COLOR = "black"
GENERATION_SHADE_ALPHA = 0.1
GENERATION_LABEL_Y = 0.98


class ViewTimeError(RuntimeError):
    """Raised when recorded timing data cannot be visualized."""


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


def _first_datetime(
    record: Mapping[str, object], keys: Sequence[str]
) -> datetime | None:
    for key in keys:
        dt = _parse_dt(record.get(key))
        if dt is not None:
            return dt
    return None


def _first_datetime_from_sources(
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


def _canonical_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status == "done":
        return "completed"
    return status or "unknown"


def _record_status(record: Mapping[str, object], metadata: Mapping[str, object]) -> str:
    return _canonical_status(record.get("status") or metadata.get("status"))


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
    return "" if message is None else " ".join(message.split())


def _normalize_machine_name(value: object) -> str | None:
    if value in (None, ""):
        return None
    name = str(value).strip().strip('"')
    if not name:
        return None
    if "@" in name:
        name = name.split("@", 1)[1]
    return name or None


def _computer_name(
    record: Mapping[str, object], metadata: Mapping[str, object]
) -> str:
    for key in (
        "execute_machine",
        "condor_execute_machine",
        "LastRemoteHost",
        "RemoteHost",
        "Machine",
        "machine",
        "hostname",
        "host_name",
    ):
        for source in (record, metadata):
            machine = _normalize_machine_name(source.get(key))
            if machine is not None:
                return machine
    status = _record_status(record, metadata)
    if status == "timeout" or any(
        _is_truthy(source.get("timed_out")) for source in (record, metadata)
    ):
        log_tail = _first_text((record, metadata), ("condor_log_tail",))
        if log_tail is not None:
            site = condor_timeout_execution_site_from_text(log_tail)
            if site is not None and site.machine is not None:
                return site.machine
    engine = _first_text((record, metadata), ("engine",))
    return "local" if str(engine or "").lower() == "local" else "unknown"


def _metadata_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_str(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value in (None, ""):
        return None
    return str(value)


def _metadata_elapsed_minutes(metadata: Mapping[str, object]) -> float | None:
    minute_keys = ("elapsed_min", "elapsed_minutes", "duration_min", "duration_minutes")
    second_keys = ("elapsed_sec", "elapsed_seconds", "duration_sec", "duration_seconds", "runtime_sec", "runtime_seconds")
    for key in minute_keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            elapsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(elapsed):
            return max(0.0, elapsed)
    for key in second_keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            elapsed = float(value) / 60.0
        except (TypeError, ValueError):
            continue
        if math.isfinite(elapsed):
            return max(0.0, elapsed)
    return None


def _elapsed_minutes(start: datetime, end: datetime, metadata: Mapping[str, object]) -> float:
    explicit = _metadata_elapsed_minutes(metadata)
    if explicit is not None:
        return explicit
    return max(0.0, (end - start).total_seconds() / 60.0)


def _as_filter_status(status: str | None) -> str | None:
    if status is None:
        return None
    clean = _canonical_status(status)
    return None if clean == "all" else clean


def build_rows(
    workspace: WorkspaceLike,
    *,
    status: str | None = None,
    recorded_api=recorded_data_api,
) -> list[dict[str, object]]:
    """Build timing rows from current recorded-data individual metadata."""

    list_records = getattr(recorded_api, "list_records", None)
    if list_records is None:
        raise ViewTimeError("recorded_data.api does not provide list_records()")

    wanted_status = _as_filter_status(status)
    opt_metadata = _opt_metadata_by_job(workspace, recorded_api)
    rows: list[dict[str, object]] = []
    skipped_without_time = 0
    for row_number, record_raw in enumerate(list_records(workspace), start=1):
        if not isinstance(record_raw, Mapping):
            continue
        record = dict(record_raw)
        metadata = _metadata(record)
        opt_row = opt_metadata.get(str(record.get("job_name") or metadata.get("job_name") or ""))
        record_status = _record_status(record, metadata)
        if wanted_status is not None and record_status != wanted_status:
            continue

        start = _first_datetime(
            record,
            ("started_at", "failed_at", "ended_at", "recorded_at"),
        )
        end = _first_datetime(
            record,
            ("ended_at", "failed_at", "recorded_at", "started_at"),
        )
        if start is None and end is None:
            skipped_without_time += 1
            continue
        if start is None:
            start = end
        if end is None:
            end = start
        assert start is not None and end is not None
        failed = record_status != "completed"
        event_time = (
            _first_datetime_from_sources(
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
            if failed
            else end
        )
        if event_time is None:
            event_time = end

        job_name = str(record.get("job_name") or metadata.get("job_name") or f"row_{row_number}")
        optimization_index = _metadata_int(record, "optimization_index")
        if optimization_index is None:
            optimization_index = _metadata_int(metadata, "optimization_index")
        if optimization_index is None:
            optimization_index = (opt_row or {}).get("optimization_index")
        generation_index = _metadata_int(record, "generation_index")
        if generation_index is None:
            generation_index = _metadata_int(metadata, "generation_index")
        if generation_index is None:
            generation_index = (opt_row or {}).get("generation_index")
        optimization_run_id = (
            _metadata_str(record, "run_id")
            or _metadata_str(metadata, "run_id")
            or (opt_row or {}).get("optimization_run_id")
        )
        rows.append(
            {
                "row_number": row_number,
                "job_name": job_name,
                "status": record_status,
                "start": start,
                "end": end,
                "event_time": event_time,
                "elapsed_min": _elapsed_minutes(start, end, metadata),
                "success": not failed,
                "failed": failed,
                "error_type": _error_type(record, metadata, record_status),
                "error_message": _error_message(record, metadata),
                "computer": _computer_name(record, metadata),
                "optimization_index": optimization_index,
                "optimization_run_id": optimization_run_id,
                "generation_index": generation_index,
                "job_static_hash": _metadata_str(metadata, "job_static_hash"),
            }
        )

    rows.sort(key=lambda row: (row["start"], row["row_number"]))  # type: ignore[index]
    if not rows:
        status_text = "all statuses" if wanted_status is None else f"status={wanted_status!r}"
        suffix = f"; skipped {skipped_without_time} records without usable timing fields" if skipped_without_time else ""
        raise ViewTimeError(f"No recorded timing rows found in recorded_data ({status_text}){suffix}.")
    return rows


def gaussian_kernel_smoother(x_data, y_data, fine_x, sigma):
    import numpy as np

    smoothed = np.zeros_like(fine_x, dtype=float)
    for i, fx in enumerate(fine_x):
        weights = np.exp(-((x_data - fx) ** 2) / (2 * sigma**2))
        weight_sum = float(np.sum(weights))
        if weight_sum > 0.0:
            smoothed[i] = np.sum(weights * y_data) / weight_sum
    return smoothed


def _categorical_colors(
    labels: Sequence[str],
    *,
    hue_offset: float = 0.0,
    saturation: float = 0.68,
    value: float = 0.78,
) -> dict[str, str]:
    unique = tuple(dict.fromkeys(str(label) for label in labels))
    count = max(1, len(unique))
    colors: dict[str, str] = {}
    for index, label in enumerate(unique):
        hue = (hue_offset + index / count) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
        colors[label] = "#{:02x}{:02x}{:02x}".format(
            round(red * 255),
            round(green * 255),
            round(blue * 255),
        )
    return colors


def _error_band_positions(error_types: Sequence[str]) -> dict[str, float]:
    unique = tuple(dict.fromkeys(str(error_type) for error_type in error_types))
    if not unique:
        return {}
    if len(unique) == 1:
        return {unique[0]: (ERROR_BAND_BOTTOM + ERROR_BAND_TOP) / 2.0}
    step = (ERROR_BAND_TOP - ERROR_BAND_BOTTOM) / (len(unique) - 1)
    return {
        error_type: ERROR_BAND_BOTTOM + index * step
        for index, error_type in enumerate(unique)
    }


def _optimization_starts(rows: Sequence[dict[str, object]]) -> list[tuple[int, datetime]]:
    starts: list[tuple[int, datetime]] = []
    seen: set[int] = set()
    for row in rows:
        opt_idx = row.get("optimization_index")
        if opt_idx is None or int(opt_idx) in seen:
            continue
        seen.add(int(opt_idx))
        starts.append((int(opt_idx), row["start"]))  # type: ignore[arg-type]
    return starts


def _time_cell_edges(rows: Sequence[dict[str, object]]) -> list[datetime]:
    times = [row["start"] for row in rows]
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
        min(positive_gaps) / 2
        if positive_gaps
        else timedelta(seconds=30)
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


def _plot_time_limits(
    rows: Sequence[dict[str, object]],
) -> tuple[datetime, datetime]:
    times = [row["start"] for row in rows]
    times.extend(row["event_time"] for row in rows if row["failed"])
    left = min(times)
    right = max(times)
    if left == right:
        margin = timedelta(seconds=30)
    else:
        margin = max(
            timedelta(seconds=1),
            (right - left) * 0.025,  # type: ignore[operator]
        )
    return left - margin, right + margin  # type: ignore[operator]


def _generation_regions(
    rows: Sequence[dict[str, object]],
) -> list[tuple[int, datetime, datetime]]:
    edges = _time_cell_edges(rows)
    regions: list[tuple[int, datetime, datetime]] = []
    active_key: tuple[object, int] | None = None
    active_generation: int | None = None
    start_index = 0

    for index, row in enumerate(rows):
        generation = _metadata_int(row, "generation_index")
        run_identity = row.get("optimization_run_id")
        if run_identity is None:
            run_identity = row.get("optimization_index")
        key = None if generation is None else (run_identity, generation)

        if key == active_key:
            continue
        if active_key is not None and active_generation is not None:
            regions.append(
                (active_generation, edges[start_index], edges[index])
            )
        active_key = key
        active_generation = generation
        start_index = index

    if active_key is not None and active_generation is not None:
        regions.append(
            (active_generation, edges[start_index], edges[len(rows)])
        )
    return regions


def _draw_generation_regions(
    ax, regions: Sequence[tuple[int, datetime, datetime]]
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
            left + (right - left) / 2,
            GENERATION_LABEL_Y,
            str(generation),
            transform=xaxis_transform,
            ha="center",
            va="top",
            color="black",
            fontsize=PLOT_GENERATION_FONT_SIZE,
            zorder=4,
        )


def _hash_change_times(rows: Sequence[dict[str, object]]) -> list[datetime]:
    starts: list[datetime] = []
    previous_hash = None
    seen_hash = False
    for row in rows:
        current_hash = row.get("job_static_hash")
        if current_hash is None:
            continue
        if seen_hash and current_hash != previous_hash:
            starts.append(row["start"])  # type: ignore[arg-type]
        previous_hash, seen_hash = current_hash, True
    return starts


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


def summarize_rows(rows: Sequence[dict[str, object]]) -> str:
    elapsed = [float(row["elapsed_min"]) for row in rows]
    completed_elapsed = [float(row["elapsed_min"]) for row in rows if row["success"]]
    failed_rows = [row for row in rows if row["failed"]]
    failure_rate = 100.0 * len(failed_rows) / len(rows)
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1
    type_counts: dict[str, int] = {}
    for row in failed_rows:
        error_type = str(row["error_type"])
        type_counts[error_type] = type_counts.get(error_type, 0) + 1
    span_end = max(
        [
            *(row["end"] for row in rows),
            *(row["event_time"] for row in failed_rows),
        ]
    )

    lines = [
        f"rows: {len(rows)}",
        f"time span: {rows[0]['start']} to {span_end}",
        f"avg elapsed: {sum(elapsed) / len(elapsed):.3f} min",
        "avg completed elapsed: "
        + ("n/a" if not completed_elapsed else f"{sum(completed_elapsed) / len(completed_elapsed):.3f} min"),
        f"errors: {len(failed_rows)}",
        f"failure rate: {failure_rate:.2f} %",
        "status counts:",
    ]
    table_rows = [[status, str(count)] for status, count in sorted(status_counts.items())]
    lines.extend(_table_lines(["status", "count"], table_rows, [False, True]))
    lines.append("error type counts:")
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
                ("time", "error type", "job", "computer", "message"),
                tuple(
                    (
                        row["event_time"].isoformat(sep=" "),  # type: ignore[union-attr]
                        str(row["error_type"]),
                        str(row["job_name"]),
                        str(row["computer"]),
                        str(row["error_message"]),
                    )
                    for row in failed_rows
                ),
                (False, False, False, False, False),
            )
        )
    else:
        lines.append("none")
    return "\n".join(lines)


def _import_plot_modules():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise ViewTimeError("matplotlib and numpy are required to render viewTime PNG output") from exc
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
            / f"time_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
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
        [(row["start"] - rows[0]["start"]).total_seconds() / 3600.0 for row in rows],  # type: ignore[operator]
        dtype=float,
    )
    elapsed = np.asarray([row["elapsed_min"] for row in rows], dtype=float)
    failures = np.asarray([row["failed"] for row in rows], dtype=float)
    time_limits = _plot_time_limits(rows)
    generation_regions = _generation_regions(rows)

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
    fine_times = [rows[0]["start"] + timedelta(hours=float(x)) for x in fine_x]  # type: ignore[operator]

    done_rows = [row for row in rows if row["success"]]
    fail_rows = [row for row in rows if row["failed"]]
    computers = tuple(dict.fromkeys(str(row["computer"]) for row in rows))
    computer_colors = _categorical_colors(computers)
    error_types = tuple(
        dict.fromkeys(str(row["error_type"]) for row in fail_rows)
    )
    error_colors = _categorical_colors(
        error_types,
        hue_offset=0.08,
        saturation=0.92,
        value=0.88,
    )
    error_positions = _error_band_positions(error_types)

    fig, ax = plt.subplots(figsize=PLOT_FIGSIZE)
    _draw_generation_regions(ax, generation_regions)

    for computer in computers:
        computer_avg = float(
            np.mean(
                [
                    float(row["elapsed_min"])
                    for row in rows
                    if str(row["computer"]) == computer
                ]
            )
        )
        ax.scatter(
            [],
            [],
            facecolors=computer_colors[computer],
            edgecolors=computer_colors[computer],
            alpha=0.75,
            s=SCATTER_MARKER_SIZE**2,
            linewidths=SCATTER_EDGE_LINE_WIDTH,
            label=f"{computer} (avg. {computer_avg:.2f} min)",
        )
        matching = [
            row for row in done_rows if str(row["computer"]) == computer
        ]
        if not matching:
            continue
        ax.scatter(
            [row["start"] for row in matching],
            [row["elapsed_min"] for row in matching],
            facecolors=computer_colors[computer],
            edgecolors=computer_colors[computer],
            alpha=0.75,
            s=SCATTER_MARKER_SIZE**2,
            linewidths=SCATTER_EDGE_LINE_WIDTH,
        )

    xaxis_transform = ax.get_xaxis_transform()
    for error_type in error_types:
        height = error_positions[error_type]
        ring_color = error_colors[error_type]
        ax.plot(
            [time_limits[0], time_limits[1]],
            [height, height],
            transform=xaxis_transform,
            color=ring_color,
            linewidth=ERROR_BAND_LINE_WIDTH,
            alpha=0.45,
            zorder=1.2,
        )
        ax.text(
            ERROR_LABEL_X,
            height,
            error_type,
            transform=ax.transAxes,
            ha="left",
            va="center",
            color=ring_color,
            fontsize=PLOT_LEGEND_FONT_SIZE,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.7,
                "pad": 0.4,
            },
            zorder=4,
        )
        for row in fail_rows:
            if str(row["error_type"]) != error_type:
                continue
            computer = str(row["computer"])
            ax.scatter(
                [row["event_time"]],
                [height],
                transform=xaxis_transform,
                facecolors=computer_colors[computer],
                edgecolors=ring_color,
                linewidths=ERROR_RING_LINE_WIDTH,
                alpha=0.95,
                s=ERROR_SCATTER_MARKER_SIZE**2,
                zorder=3,
            )

    if done_rows:
        done_x = np.asarray(
            [(row["start"] - rows[0]["start"]).total_seconds() / 3600.0 for row in done_rows],  # type: ignore[operator]
            dtype=float,
        )
        done_y = np.asarray([row["elapsed_min"] for row in done_rows], dtype=float)
        global_avg = float(np.mean(done_y))
        local_avg = gaussian_kernel_smoother(done_x, done_y, fine_x, sigma)
        ax.plot(
            fine_times,
            local_avg,
            color="orange",
            linewidth=TREND_LINE_WIDTH,
            alpha=TREND_LINE_ALPHA,
            label=f"avg. time (global: {global_avg:.2f} min)",
        )

    global_failure = float(np.mean(failures) * 100.0)
    local_failure = (
        gaussian_kernel_smoother(x_hours, failures, fine_x, sigma) * 100.0
    )
    ax2 = ax.twinx()
    ax2.plot(
        fine_times,
        local_failure,
        color=FAIL_RATE_COLOR,
        linewidth=TREND_LINE_WIDTH,
        alpha=FAIL_RATE_LINE_ALPHA,
        label=f"avg. failure rate (global: {global_failure:.2f} %)",
    )

    event_line_style = {
        "linewidth": EVENT_LINE_WIDTH,
        "alpha": EVENT_LINE_ALPHA,
        "dash_capstyle": "butt",
        "zorder": 0.7,
    }
    first_opt = True
    for _, when in _optimization_starts(rows):
        ax.axvline(
            when,
            color=OPT_LINE_COLOR,
            linestyle=OPT_LINE_STYLE,
            label=OPT_LINE_LABEL if first_opt else None,
            **event_line_style,
        )
        first_opt = False

    first_hash = True
    for when in _hash_change_times(rows):
        ax.axvline(
            when,
            color=HASH_LINE_COLOR,
            linestyle=HASH_LINE_STYLE,
            label=HASH_LINE_LABEL if first_hash else None,
            **event_line_style,
        )
        first_hash = False

    ax.set_xlabel("Time", fontsize=PLOT_FONT_SIZE)
    ax.set_ylabel("Elapsed time (minutes)", fontsize=PLOT_FONT_SIZE)
    ax.set_title(
        "Evaluation time and failures from recorded_data",
        fontsize=PLOT_TITLE_FONT_SIZE,
    )
    ax.set_xlim(time_limits[0], time_limits[1])
    ax.grid(
        True,
        color="gainsboro",
        linestyle="-",
        linewidth=GRID_LINE_WIDTH,
        alpha=0.6,
    )
    completed_max = (
        max(float(row["elapsed_min"]) for row in done_rows)
        if done_rows
        else 0.0
    )
    ax.set_ylim(0.0, max(1.0, completed_max / ELAPSED_DATA_TOP))
    ax.tick_params(
        axis="both",
        labelsize=PLOT_TICK_FONT_SIZE,
        width=AXIS_LINE_WIDTH,
    )

    ax2.set_ylabel("Failure rate (%)", fontsize=PLOT_FONT_SIZE)
    ax2.set_ylim(0.0, 100.0)
    ax2.tick_params(
        axis="both",
        labelsize=PLOT_TICK_FONT_SIZE,
        width=AXIS_LINE_WIDTH,
    )

    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    fig.tight_layout(pad=PLOT_TIGHT_LAYOUT_PAD)
    _add_split_legends(ax, (ax, ax2))
    fig.savefig(output, dpi=PLOT_DPI)
    plt.close(fig)
    return output


def view_time(
    workspace: WorkspaceLike,
    *,
    status: str | None = None,
    output_path: str | Path | None = None,
) -> tuple[str, Path | None]:
    """Return a timing summary and optionally render a PNG."""

    config = load_config(workspace)
    rows = build_rows(config.workspace, status=_as_filter_status(status))
    summary = summarize_rows(rows)
    output = (
        None
        if output_path is None
        else plot_rows(config.workspace, rows, output_path)
    )
    return summary, output


__all__ = [
    "ViewTimeError",
    "build_rows",
    "plot_rows",
    "summarize_rows",
    "view_time",
]
