"""Foreground-owned Rich presentation for measured benchmark commands."""
from __future__ import annotations

import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from rich.console import Console
from rich.progress import Progress, ProgressColumn, Task, TextColumn
from rich.table import Column
from rich.text import Text

CONSOLE_LOG_NAME = "benchmark.log"


class _AsciiBarColumn(ProgressColumn):
    """Render a compact Rich-owned bar on legacy Windows code pages."""

    def __init__(self, width: int) -> None:
        self.width = max(1, int(width))
        column_width = self.width + 2
        super().__init__(
            Column(
                width=column_width,
                min_width=column_width,
                max_width=column_width,
                no_wrap=True,
            )
        )

    def render(self, task: Task) -> Text:
        if task.total is None:
            filled = 0
        elif task.total <= 0:
            filled = self.width
        else:
            ratio = min(1.0, max(0.0, task.completed / task.total))
            filled = min(self.width, math.ceil(self.width * ratio)) if ratio else 0
        return Text(f"[{'#' * filled}{'-' * (self.width - filled)}]")


class BenchmarkTerminal:
    """Keep active-cell and global progress below ordinary lifecycle output."""

    def __init__(
        self,
        run: str | Path | None = None,
        *,
        stream: Any | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.stream = sys.stderr if stream is None else stream
        self._owner_thread = threading.get_ident()
        self._environment = dict(os.environ if environ is None else environ)
        self.interactive = bool(getattr(self.stream, "isatty", lambda: False)())
        console_environment = dict(self._environment)
        if self.interactive and console_environment.get("TERM", "").lower() in {
            "dumb",
            "unknown",
        }:
            console_environment.pop("TERM", None)
        self.console = Console(
            file=self.stream,
            force_terminal=self.interactive,
            force_interactive=self.interactive,
            color_system=None,
            no_color="NO_COLOR" in self._environment,
            legacy_windows=False,
            _environ=console_environment,
        )
        width = max(20, int(self.console.width))
        self._compact = width < 88
        self._very_compact = width < 56
        bar_width = 18 if width >= 88 else 10 if width >= 64 else 5 if width >= 48 else 1
        self._bar_width = bar_width
        self._progress = Progress(
            TextColumn(
                "{task.fields[label]}",
                markup=False,
                table_column=Column(
                    width=11,
                    min_width=11,
                    max_width=11,
                    no_wrap=True,
                ),
            ),
            _AsciiBarColumn(bar_width),
            TextColumn(
                "{task.fields[detail]}",
                markup=False,
                table_column=Column(min_width=1, overflow="crop", no_wrap=True),
            ),
            console=self.console,
            auto_refresh=False,
            transient=True,
            redirect_stdout=False,
            redirect_stderr=False,
            disable=not self.interactive,
        )
        self.total_cells = 0
        self.finished_cells = 0
        self.completed_cells = 0
        self.failed_cells = 0
        self.current_cell: str | None = None
        self.cell_total = 0
        self.cell_completed = 0
        self.cell_successful = 0
        self.cell_errors = 0
        self.generation_number: int | None = None
        self.generations = 0
        self.phase = "waiting"
        self._cell_task = self._progress.add_task(
            "",
            total=1,
            completed=0,
            visible=True,
            label="[cell]",
            detail=self._cell_detail(),
        )
        self._global_task = self._progress.add_task(
            "",
            total=1,
            completed=0,
            visible=True,
            label="[benchmark]",
            detail=self._global_detail(),
        )
        self._active = False
        self._plain_bucket = -1
        self._last_progress_log = 0.0
        self._log_path: Path | None = None
        if run is not None:
            self._bind_run(run)

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    def _check_owner(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("benchmark terminal updates must use the owner thread")

    def _bind_run(self, run: str | Path) -> None:
        root = Path(run).resolve()
        self._log_path = root / CONSOLE_LOG_NAME

    def _append_log(self, text: str) -> None:
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(text.rstrip("\r\n") + "\n")
            stream.flush()

    @staticmethod
    def _percentage(completed: int, total: int) -> str:
        if total <= 0:
            return "0%"
        value = min(100.0, max(0.0, 100.0 * completed / total))
        return f"{value:.1f}%" if 0.0 < value < 10.0 else f"{value:.0f}%"

    @staticmethod
    def _bar(completed: int, total: int, width: int) -> str:
        ratio = 0.0 if total <= 0 else min(1.0, max(0.0, completed / total))
        filled = min(width, math.ceil(width * ratio)) if ratio else 0
        return "#" * filled + "-" * (width - filled)

    def _cell_detail(self) -> str:
        phase = self._compact_phase()
        if self._very_compact:
            generation = f"g{self.generation_number or '-'}/{self.generations or '-'}"
            return (
                f"{self.cell_completed}/{self.cell_total} {generation} "
                f"e{self.cell_errors} {phase}"
            )
        percentage = self._percentage(self.cell_completed, self.cell_total)
        generation = (
            f"g{self.generation_number or '-'}/{self.generations or '-'}"
            if self._compact
            else f"gen={self.generation_number or '-'}/{self.generations or '-'}"
        )
        if self._compact:
            return (
                f"{self.cell_completed}/{self.cell_total} {percentage} {generation} "
                f"o{self.cell_successful} e{self.cell_errors} {phase}"
            )
        return (
            f"{self.cell_completed}/{self.cell_total} eval | {percentage} "
            f"{generation} ok={self.cell_successful} err={self.cell_errors} "
            f"phase={self.phase}"
        )

    def _compact_phase(self) -> str:
        if self.phase.startswith("generation"):
            return "run"
        aliases = {
            "baseline-postprocess": "post",
            "view-cost": "view",
            "completed": "done",
            "collected": "done",
        }
        return aliases.get(self.phase, self.phase[:8])

    def _global_detail(self) -> str:
        if self._compact:
            return (
                f"{self.finished_cells}/{self.total_cells} "
                f"ok{self.completed_cells} e{self.failed_cells}"
            )
        return (
            f"{self.finished_cells}/{self.total_cells} cells | "
            f"ok={self.completed_cells} err={self.failed_cells}"
        )

    def _cell_line(self) -> str:
        bar = self._bar(self.cell_completed, self.cell_total, self._bar_width)
        return f"[cell] [{bar}] {self._cell_detail()}"

    def _global_line(self) -> str:
        bar = self._bar(self.finished_cells, self.total_cells, self._bar_width)
        return f"[benchmark] [{bar}] {self._global_detail()}"

    def _refresh(self) -> None:
        if not self.interactive or not self._active:
            return
        self._progress.update(
            self._cell_task,
            total=max(1, self.cell_total),
            completed=self.cell_completed,
            detail=self._cell_detail(),
            refresh=False,
        )
        self._progress.update(
            self._global_task,
            total=max(1, self.total_cells),
            completed=self.finished_cells,
            detail=self._global_detail(),
            refresh=False,
        )
        self._progress.refresh()

    def _write_plain_snapshot(self) -> None:
        self.stream.write(self._cell_line() + "\n")
        self.stream.write(self._global_line() + "\n")
        self.stream.flush()

    def _write_above(self, text: str) -> None:
        normalized = text.rstrip("\r\n")
        if self.interactive and self._active:
            self.console.print(
                normalized,
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        else:
            self.stream.write(normalized + "\n")
            self.stream.flush()
        self._append_log(normalized)

    def start(self) -> None:
        self._check_owner()
        if self._active:
            return
        self._active = True
        if self.interactive:
            self._progress.start()
            self._refresh()
        else:
            self._write_plain_snapshot()

    def _apply_global(self, event: Mapping[str, Any]) -> None:
        if "total_cells" not in event:
            return
        self.total_cells = int(event["total_cells"])
        self.finished_cells = int(event["finished_cells"])
        self.completed_cells = int(event["completed_cells"])
        self.failed_cells = int(event["failed_cells"])

    def handle(self, event: Mapping[str, Any]) -> None:
        self._check_owner()
        kind = str(event.get("event", ""))
        if event.get("run"):
            self._bind_run(str(event["run"]))
        self._apply_global(event)
        if kind == "cell-started":
            if event.get("previous_status") == "failed" or event.get("previous_error"):
                self.failed_cells = max(0, self.failed_cells - 1)
                self.finished_cells = max(0, self.finished_cells - 1)
            self.current_cell = str(event.get("cell", ""))
            self.cell_total = int(event.get("planned_evaluations", 0))
            self.cell_completed = 0
            self.cell_successful = 0
            self.cell_errors = 0
            self.generation_number = None
            self.generations = int(event.get("generations", 0))
            self.phase = "preparing"
            self._plain_bucket = -1
        elif kind == "command-started":
            self.phase = str(event.get("label", "command"))
        elif kind == "command-progress":
            self.phase = str(event.get("label", self.phase))
        elif kind == "cell-progress":
            self.cell_completed = max(
                self.cell_completed, int(event.get("evaluations", 0))
            )
            self.cell_total = max(
                self.cell_total, int(event.get("planned_evaluations", 0))
            )
            number = event.get("generation_number")
            self.generation_number = None if number is None else int(number)
            self.generations = max(self.generations, int(event.get("generations", 0)))
            self.cell_successful = int(event.get("successful", 0))
            self.cell_errors = int(event.get("errors", 0))
            self.phase = str(event.get("phase", "run"))
        elif kind == "command-finished":
            self.phase = f"{event.get('label', 'command')}:{event.get('returncode', '?')}"
            if event.get("label") == "run" and int(event.get("returncode", 1)) == 0:
                self.cell_completed = self.cell_total
        elif kind == "cell-collected":
            self.cell_completed = self.cell_total
            self.phase = "collected"
        elif kind in {"cell-failed", "collection-failed", "visualization-failed"}:
            self.phase = "failed"
        elif kind == "run-finished":
            self.phase = str(event.get("status", "finished"))

        message = _event_message(event)
        if message:
            self._write_above(message)
        if kind == "cell-progress":
            now = time.monotonic()
            terminal = self.cell_completed >= self.cell_total > 0
            if now - self._last_progress_log >= 5.0 or terminal:
                self._append_log(f"{event.get('utc', '')} {self._cell_line()}")
                self._last_progress_log = now
        if self.interactive:
            self._refresh()
            return
        if kind == "cell-progress":
            bucket = min(
                10,
                int(10 * self.cell_completed / max(1, self.cell_total)),
            )
            if self.cell_completed > 0 and self._plain_bucket < 0:
                self._plain_bucket = 0
                self._write_plain_snapshot()
            elif bucket > self._plain_bucket:
                self._plain_bucket = bucket
                self._write_plain_snapshot()
        elif kind in {
            "run-started",
            "cell-started",
            "cell-collected",
            "cell-failed",
            "collection-failed",
            "visualization-failed",
            "run-finished",
        }:
            self._write_plain_snapshot()

    def finish(
        self,
        *,
        result: Mapping[str, Any] | None = None,
        error: BaseException | str | None = None,
    ) -> None:
        self._check_owner()
        if not self._active:
            return
        if self.interactive:
            self._progress.stop()
        self._active = False
        if error is not None:
            message = f"benchmark failed: {error}"
        elif result is not None:
            message = (
                f"benchmark finished: status={result.get('status')} "
                f"run={result.get('run')}"
            )
        else:
            message = "benchmark terminal stopped"
        self._write_above(message)


def _event_message(event: Mapping[str, Any]) -> str | None:
    kind = str(event.get("event", ""))
    utc = str(event.get("utc", ""))
    prefix = f"{utc} " if utc else ""
    if kind == "run-created":
        return f"{prefix}[benchmark] run created; run={event.get('run')}"
    if kind == "run-started":
        return f"{prefix}[benchmark] started; run={event.get('run')}"
    if kind == "cell-started":
        return f"{prefix}[cell] {event.get('cell')} started"
    if kind == "command-started":
        return (
            f"{prefix}[{event.get('label')}] started; pid={event.get('pid')} "
            f"log_dir={event.get('log_dir')}"
        )
    if kind == "command-finished":
        return (
            f"{prefix}[{event.get('label')}] finished; "
            f"returncode={event.get('returncode')} "
            f"duration={event.get('duration_seconds')}s"
        )
    if kind == "child-output":
        return f"[{event.get('stream', 'child')}] {event.get('text', '')}"
    if kind == "cell-collected":
        return f"{prefix}[cell] {event.get('cell')} collected"
    if kind in {"cell-failed", "collection-failed", "visualization-failed"}:
        return f"{prefix}[cell] {event.get('cell')} failed; {event.get('error')}"
    if kind == "postprocessor-started":
        return f"{prefix}[postprocess] {event.get('postprocessor')} started"
    if kind == "postprocessor-finished":
        return f"{prefix}[postprocess] {event.get('postprocessor')} finished"
    if kind == "postprocessor-failed":
        return (
            f"{prefix}[postprocess] {event.get('postprocessor')} failed; "
            f"{event.get('error')}"
        )
    if kind == "run-finished":
        return f"{prefix}[benchmark] finished; status={event.get('status')}"
    return None


__all__ = ["BenchmarkTerminal", "CONSOLE_LOG_NAME"]
