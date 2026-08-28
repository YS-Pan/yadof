"""Progress services for benchmark automation."""
from __future__ import annotations
import contextlib
import dataclasses
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import queue
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from rich.console import Console
from rich.progress import Progress, ProgressColumn, Task, TextColumn
from rich.table import Column
from rich.text import Text
from .contracts import *
from .contracts import YADOF_PROGRESS as _YADOF_PROGRESS

class _AsciiBarColumn(ProgressColumn):
    """Render a fixed-width Rich bar on legacy Windows code pages."""

    def __init__(self, width: int) -> None:
        self.width = max(1, int(width))
        column_width = self.width + 2
        super().__init__(Column(width=column_width, min_width=column_width, max_width=column_width, no_wrap=True))

    def render(self, task: Task) -> Text:
        if task.total is None:
            finished = 0
        elif task.total <= 0:
            finished = self.width
        else:
            ratio = min(1.0, max(0.0, task.completed / task.total))
            finished = min(self.width, math.ceil(self.width * ratio)) if ratio else 0
        return Text(f"[{'#' * finished}{'-' * (self.width - finished)}]")

def _parse_yadof_progress(line: str) -> dict[str, Any] | None:
    """Parse one complete yadof progress snapshot from a piped child stream."""
    match = _YADOF_PROGRESS.fullmatch(line.strip())
    if match is None:
        return None
    generation_text = match.group('generation')
    generation = int(generation_text) if generation_text is not None else None
    finished = int(match.group('finished'))
    total = max(1, int(match.group('total')))
    return {'phase': match.group('phase'), 'generation': generation, 'finished': finished, 'total': total, 'absolute_finished': finished if generation is None else generation * total + finished, 'successful': int(match.group('successful')), 'errors': int(match.group('errors')), 'remaining': int(match.group('remaining'))}

class CellProgress:
    """Keep Rich-managed cell and run progress below lifecycle messages."""

    def __init__(self, total: int, *, completed: int=0, stream: Any | None=None, width: int=18) -> None:
        self.total = max(0, int(total))
        self.finished = max(0, int(completed))
        self.completed = max(0, int(completed))
        self.failed = 0
        self.skipped = 0
        self.current: str | None = None
        self.stream = sys.stderr if stream is None else stream
        self.width = max(10, int(width))
        self.interactive = bool(getattr(self.stream, 'isatty', lambda: False)())
        self._active = False
        self._lock = threading.RLock()
        self._cell_total = 0
        self._cell_completed = 0
        self._cell_detail = ''
        self._noninteractive_bucket = -1
        console_environment: Mapping[str, str] | None = None
        if self.interactive and os.environ.get('TERM', '').lower() in {'dumb', 'unknown'}:
            console_environment = dict(os.environ)
            console_environment.pop('TERM', None)
        self._console = Console(file=self.stream, force_terminal=self.interactive, force_interactive=self.interactive, color_system=None, legacy_windows=False, _environ=console_environment)
        self._progress = Progress(TextColumn('{task.fields[label]}', markup=False, table_column=Column(width=11, min_width=11, max_width=11, no_wrap=True)), _AsciiBarColumn(self.width), TextColumn('{task.fields[detail]}', markup=False, table_column=Column(min_width=1, overflow='crop', no_wrap=True)), console=self._console, auto_refresh=False, transient=True, redirect_stdout=False, redirect_stderr=False, disable=not self.interactive)
        self._cell_task = self._progress.add_task('', total=1, completed=0, visible=False, label='[cell]', detail='')
        self._global_task = self._progress.add_task('', total=self.total, completed=self.finished, label='[benchmark]', detail=self._global_detail())

    @staticmethod
    def _bar(finished: int, total: int, width: int) -> str:
        ratio = 1.0 if total == 0 else min(1.0, finished / total)
        filled = min(width, math.ceil(width * ratio)) if ratio else 0
        return '#' * filled + '-' * (width - filled)

    def _global_detail(self) -> str:
        return f'{self.finished}/{self.total} cells | ok={self.completed} err={self.failed} skip={self.skipped}'

    def _global_line(self) -> str:
        bar = self._bar(self.finished, self.total, self.width)
        return f'[benchmark] [{bar}] {self._global_detail()}'

    def _cell_line(self) -> str:
        bar = self._bar(self._cell_completed, self._cell_total, self.width)
        return f"[cell] {self.current or '-'} [{bar}] {self._cell_display_detail()}"

    def _cell_display_detail(self) -> str:
        if self._cell_total <= 0:
            percentage_text = '0%'
        else:
            percentage = min(100.0, 100.0 * self._cell_completed / self._cell_total)
            percentage_text = f'{percentage:.1f}%' if 0.0 < percentage < 10.0 else f'{percentage:.0f}%'
        return f'{self._cell_completed}/{self._cell_total} eval | {percentage_text} {self._cell_detail}'

    def _update_rich_locked(self) -> None:
        self._progress.update(self._global_task, total=self.total, completed=self.finished, detail=self._global_detail(), refresh=False)
        self._progress.update(self._cell_task, total=max(1, self._cell_total), completed=self._cell_completed, visible=self.current is not None, label='[cell]', detail=self._cell_display_detail(), refresh=False)
        self._progress.refresh()

    def _write_snapshot_locked(self, *, include_cell: bool) -> None:
        if include_cell and self.current is not None:
            self.stream.write(f'{self._cell_line()}\n')
        self.stream.write(f'{self._global_line()}\n')
        self.stream.flush()

    def start(self) -> None:
        with self._lock:
            self._active = True
            if self.interactive:
                self._progress.start()
            else:
                self._write_snapshot_locked(include_cell=False)

    def start_cell(self, cell: Mapping[str, Any]) -> None:
        with self._lock:
            self.current = str(cell['cell_id'])
            planned = int(cell.get('planned_attempted_evaluations', 0))
            if planned <= 0:
                planned = max(1, int(cell.get('population', 1)) * max(1, int(cell.get('generations', 1))))
            self._cell_total = planned
            self._cell_completed = 0
            self._cell_detail = 'phase=preparing'
            self._noninteractive_bucket = 0
            if self.interactive:
                self._update_rich_locked()
            else:
                self._write_snapshot_locked(include_cell=True)

    def set_phase(self, phase: str) -> None:
        with self._lock:
            if self.current is None:
                return
            self._cell_detail = f'phase={phase}'
            if self.interactive:
                self._update_rich_locked()

    def extend_current(self, evaluations: int) -> None:
        with self._lock:
            if self.current is None:
                return
            self._cell_total += max(0, int(evaluations))
            if self.interactive:
                self._update_rich_locked()
            else:
                self._noninteractive_bucket = int(10 * self._cell_completed / max(1, self._cell_total))

    def observe_yadof_line(self, line: str) -> bool:
        """Convert one child yadof snapshot into the active cell progress task."""
        snapshot = _parse_yadof_progress(line)
        if snapshot is None:
            return False
        self.observe_yadof_snapshot(snapshot)
        return True

    def observe_yadof_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Apply one already parsed yadof snapshot to the active cell task."""
        with self._lock:
            if self.current is None:
                return
            total = int(snapshot['total'])
            generation = snapshot['generation']
            absolute_finished = int(snapshot['absolute_finished'])
            if absolute_finished > self._cell_total:
                self._cell_total = absolute_finished
            self._cell_completed = max(self._cell_completed, absolute_finished)
            if generation is None:
                phase = 'smoke'
            else:
                generation_number = generation + 1
                generation_count = max(generation_number, (self._cell_total + total - 1) // total)
                phase = f'gen={generation_number}/{generation_count}'
            self._cell_detail = f"{phase} ok={snapshot['successful']} err={snapshot['errors']}"
            if self.interactive:
                self._update_rich_locked()
            else:
                bucket = min(10, int(10 * self._cell_completed / max(1, self._cell_total)))
                if bucket > self._noninteractive_bucket:
                    self._noninteractive_bucket = bucket
                    self._write_snapshot_locked(include_cell=True)

    def write_above(self, text: str, *, console: Any | None=None) -> None:
        target = self.stream if console is None else console
        with self._lock:
            if self.interactive:
                normalized = text if text.endswith(('\n', '\r')) else f'{text}\n'
                self._console.print(normalized, end='', markup=False, highlight=False, soft_wrap=True)
            else:
                target.write(text)
                target.flush()

    def advance(self, status: str) -> None:
        with self._lock:
            had_cell = self.current is not None
            if had_cell:
                if status == 'completed':
                    self._cell_completed = self._cell_total
                self._cell_detail = f'status={status}'
                if self.interactive:
                    self._update_rich_locked()
                else:
                    self.stream.write(f'{self._cell_line()}\n')
            self.finished = min(self.total, self.finished + 1)
            if status == 'completed':
                self.completed += 1
            elif status == 'failed':
                self.failed += 1
            elif status == 'skipped':
                self.skipped += 1
            self.current = None
            if self.interactive:
                self._update_rich_locked()
            else:
                self._write_snapshot_locked(include_cell=False)

    def finish(self) -> None:
        with self._lock:
            if not self._active:
                return
            if self.interactive:
                self._progress.stop()
            self._active = False


parse_yadof_progress = _parse_yadof_progress
