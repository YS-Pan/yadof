from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

try:
    from project.recorded_data import api as recorded_data_api
except ImportError:  # Allows running as ``python tools/viewTime.py`` from project/.
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT.parent))
    from project.recorded_data import api as recorded_data_api


TOOLS_DIR = Path(__file__).resolve().parent
DONE_COLOR = "#d62728"
FAIL_COLOR = "#7f7f7f"
FAIL_RATE_COLOR = "darkblue"
HASH_LINE_COLOR = "#FFAA00"
OPT_LINE_COLOR = "gray"


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


def _first_datetime(record: Mapping[str, object], metadata: Mapping[str, object], keys: Sequence[str]) -> datetime | None:
    for key in keys:
        dt = _parse_dt(metadata.get(key))
        if dt is not None:
            return dt
        dt = _parse_dt(record.get(key))
        if dt is not None:
            return dt
    return None


def _canonical_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status == "done":
        return "completed"
    return status or "unknown"


def _record_status(record: Mapping[str, object], metadata: Mapping[str, object]) -> str:
    return _canonical_status(record.get("status") or metadata.get("status"))


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


def build_rows(recorded_api=recorded_data_api, *, status: str | None = None) -> list[dict[str, object]]:
    """Build timing rows from the v3 recorded_data manifest."""

    list_records = getattr(recorded_api, "list_records", None)
    if list_records is None:
        raise ViewTimeError("recorded_data.api does not provide list_records()")

    wanted_status = _as_filter_status(status)
    rows: list[dict[str, object]] = []
    skipped_without_time = 0
    for row_number, record_raw in enumerate(list_records(), start=1):
        if not isinstance(record_raw, Mapping):
            continue
        record = dict(record_raw)
        metadata = _metadata(record)
        record_status = _record_status(record, metadata)
        if wanted_status is not None and record_status != wanted_status:
            continue

        start = _first_datetime(
            record,
            metadata,
            ("started_at", "created_at", "failed_at", "ended_at", "recorded_at"),
        )
        end = _first_datetime(
            record,
            metadata,
            ("ended_at", "failed_at", "recorded_at", "started_at", "created_at"),
        )
        if start is None and end is None:
            skipped_without_time += 1
            continue
        if start is None:
            start = end
        if end is None:
            end = start
        assert start is not None and end is not None

        job_name = str(record.get("job_name") or metadata.get("job_name") or f"row_{row_number}")
        rows.append(
            {
                "row_number": row_number,
                "job_name": job_name,
                "status": record_status,
                "start": start,
                "end": end,
                "elapsed_min": _elapsed_minutes(start, end, metadata),
                "success": record_status == "completed",
                "optimization_index": _metadata_int(metadata, "optimization_index"),
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
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1

    failure_count = len(rows) - status_counts.get("completed", 0)
    failure_rate = 100.0 * failure_count / len(rows)
    lines = [
        f"rows: {len(rows)}",
        f"time span: {rows[0]['start']} to {rows[-1]['end']}",
        f"avg elapsed: {sum(elapsed) / len(elapsed):.3f} min",
        "avg completed elapsed: "
        + ("n/a" if not completed_elapsed else f"{sum(completed_elapsed) / len(completed_elapsed):.3f} min"),
        f"failure rate: {failure_rate:.2f} %",
        "status counts:",
    ]
    table_rows = [[status, str(count)] for status, count in sorted(status_counts.items())]
    lines.extend(_table_lines(["status", "count"], table_rows, [False, True]))
    return "\n".join(lines)


def _import_plot_modules():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise ViewTimeError("matplotlib is required to render viewTime PNG output") from exc
    return plt, np, mdates


def plot_rows(rows: Sequence[dict[str, object]], output_path: str | Path | None = None) -> Path:
    plt, np, mdates = _import_plot_modules()

    if output_path is None:
        output = TOOLS_DIR / f"time_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    else:
        output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = 12

    x_hours = np.asarray(
        [(row["start"] - rows[0]["start"]).total_seconds() / 3600.0 for row in rows],  # type: ignore[operator]
        dtype=float,
    )
    elapsed = np.asarray([row["elapsed_min"] for row in rows], dtype=float)
    success = np.asarray([row["success"] for row in rows], dtype=bool)

    if len(x_hours) == 1:
        fine_x = x_hours.copy()
        sigma = 1.0
    else:
        fine_x = np.linspace(float(np.min(x_hours)), float(np.max(x_hours)), 600)
        avg_spacing = float(np.mean(np.diff(x_hours)))
        sigma = max(1e-12, max(1, int(0.05 * len(rows))) * avg_spacing / 3.0)
    fine_times = [rows[0]["start"] + timedelta(hours=float(x)) for x in fine_x]  # type: ignore[operator]

    done_rows = [row for row in rows if row["success"]]
    fail_rows = [row for row in rows if not row["success"]]

    fig, ax = plt.subplots(figsize=(12, 7))

    if done_rows:
        ax.scatter(
            [row["start"] for row in done_rows],
            [row["elapsed_min"] for row in done_rows],
            color=DONE_COLOR,
            alpha=0.6,
            s=36,
            label="completed",
        )
    if fail_rows:
        ax.scatter(
            [row["start"] for row in fail_rows],
            [row["elapsed_min"] for row in fail_rows],
            color=FAIL_COLOR,
            alpha=0.8,
            s=48,
            marker="x",
            label="not completed",
        )

    if done_rows:
        done_x = np.asarray(
            [(row["start"] - rows[0]["start"]).total_seconds() / 3600.0 for row in done_rows],  # type: ignore[operator]
            dtype=float,
        )
        done_y = np.asarray([row["elapsed_min"] for row in done_rows], dtype=float)
        global_avg = float(np.mean(done_y))
        local_avg = gaussian_kernel_smoother(done_x, done_y, fine_x, sigma)
        ax.plot(fine_times, local_avg, color="orange", linewidth=2, label=f"avg. time (global: {global_avg:.2f} min)")

    failure = (~success).astype(float)
    global_failure = float(np.mean(failure) * 100.0)
    local_failure = gaussian_kernel_smoother(x_hours, failure, fine_x, sigma) * 100.0

    ax2 = ax.twinx()
    ax2.plot(
        fine_times,
        local_failure,
        color=FAIL_RATE_COLOR,
        linewidth=2,
        alpha=0.5,
        label=f"avg. failure rate (global: {global_failure:.2f} %)",
    )

    first_opt = True
    for opt_idx, when in _optimization_starts(rows):
        ax.axvline(when, color=OPT_LINE_COLOR, linestyle="--", linewidth=0.8, alpha=0.25, label="Optimization start" if first_opt else None)
        ax.text(when, 1.01, f"opt {opt_idx}", transform=ax.get_xaxis_transform(), rotation=90, va="bottom", ha="right", fontsize=8, color=OPT_LINE_COLOR)
        first_opt = False

    first_hash = True
    for when in _hash_change_times(rows):
        ax.axvline(when, color=HASH_LINE_COLOR, linestyle="-", linewidth=1.4, alpha=0.25, label="Static input hash change" if first_hash else None)
        first_hash = False

    ax.set_xlabel("Time")
    ax.set_ylabel("Elapsed time (minutes)")
    ax.set_title("Evaluation speeds from recorded_data")
    ax.grid(True, color="gainsboro", linestyle="-", linewidth=0.5, alpha=0.6)
    ax.set_ylim(0.0, max(1.0, float(np.max(elapsed)) * 1.1))

    ax2.set_ylabel("Failure rate (%)")
    ax2.set_ylim(0.0, 100.0)

    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    legend = {}
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    for handle, label in list(zip(handles1, labels1)) + list(zip(handles2, labels2)):
        legend.setdefault(label, handle)
    ax.legend(list(legend.values()), list(legend.keys()), loc="upper left")

    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize recorded_data job timing and failure rate.")
    parser.add_argument("-o", "--output", type=Path, help="PNG output path. Defaults to project/tools/time_TIMESTAMP.png.")
    parser.add_argument("--status", default="all", help="Record status to include. Defaults to 'all'.")
    parser.add_argument("--summary-only", action="store_true", help="Print timing summary without rendering PNG.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    status = _as_filter_status(args.status)
    try:
        rows = build_rows(status=status)
        print(summarize_rows(rows))
        if not args.summary_only:
            output = plot_rows(rows, args.output)
            print(f"saved: {output}")
    except ViewTimeError as exc:
        print(f"viewTime error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
