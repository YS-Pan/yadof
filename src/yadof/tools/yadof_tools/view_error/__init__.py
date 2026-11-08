"""Typed, read-only failure rows shared by desktop entry points."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yadof.config import load_config

@dataclass(frozen=True)
class FailureRow:
    event_time: datetime
    job_name: str
    worker: str
    error_type: str
    error_message: str
    job_dir: Path | None

    @property
    def display(self) -> tuple[str, ...]:
        return (
            self.event_time.isoformat(sep=" ", timespec="milliseconds"),
            self.worker,
            self.job_name,
            self.error_type,
            self.error_message or "无详细信息",
        )


FAILURE_COLUMNS = ("event_time", "worker", "job_name", "error_type", "error_message")


FAILURE_HEADERS = ("时间", "Worker", "Job", "错误类型", "错误信息")


def failure_sort_key(row: FailureRow, column: str):
    if column not in FAILURE_COLUMNS:
        raise ValueError(f"Unknown failure column: {column}")
    value = getattr(row, column)
    return value if column == "event_time" else str(value).casefold()


def _job_dir_for_name(jobs_dir: Path, job_name: str) -> Path | None:
    if not job_name or Path(job_name).name != job_name:
        return None
    root = jobs_dir.resolve()
    candidate = (root / job_name).resolve()
    return candidate if candidate.parent == root else None


def failure_rows(workspace: Path) -> list[FailureRow]:
    """Use the time tool's failure rows and the configured workspace jobs root."""

    from yadof.tools.yadof_tools.view_time import ViewTimeError, build_rows

    try:
        rows = [row for row in build_rows(workspace) if row["failed"]]
    except ViewTimeError as exc:
        if "No recorded timing rows" in str(exc):
            return []
        raise
    if not rows:
        return []
    jobs_dir = load_config(workspace).workspace.jobs_dir
    return [FailureRow(
        event_time=row["event_time"],
        job_name=str(row["job_name"]),
        worker=str(row.get("computer") or "unknown"),
        error_type=str(row["error_type"]),
        error_message=str(row["error_message"] or ""),
        job_dir=_job_dir_for_name(jobs_dir, str(row["job_name"])),
    ) for row in rows]
