"""Execution services for benchmark automation."""
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

def _stream_pipe(pipe: Any, output: Path, console: Any | None, prefix: str, progress: CellProgress | None=None, display_events: queue.Queue[tuple[str, Any, Any | None, str]] | None=None) -> None:
    from .progress import CellProgress, parse_yadof_progress as _parse_yadof_progress
    from .storage import utc_now
    with output.open('x', encoding='utf-8', errors='replace', newline='\n') as target:
        while True:
            raw = pipe.readline()
            if not raw:
                break
            line = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else str(raw)
            target.write(line)
            target.flush()
            snapshot = _parse_yadof_progress(line) if progress is not None or display_events is not None else None
            is_progress = snapshot is not None
            if snapshot is not None:
                snapshot = {'schema_version': SCHEMA_VERSION, 'event': 'progress', 'observed_utc': utc_now(), **snapshot}
            if display_events is not None and (is_progress or console is not None):
                display_events.put(('progress' if is_progress else 'output', snapshot if is_progress else line, console, prefix))
            elif is_progress:
                progress.observe_yadof_snapshot(snapshot)
            elif console is not None:
                if progress is None:
                    console.write(f'{prefix}{line}')
                    console.flush()
                else:
                    progress.write_above(f'{prefix}{line}', console=console)

def _render_stream_events(display_events: queue.Queue[tuple[str, Any, Any | None, str]], progress: CellProgress | None, progress_events: Any | None=None) -> None:
    """Render queued child-stream events from the foreground owner thread."""
    from .progress import CellProgress
    from .storage import canonical_json
    pending_progress: Mapping[str, Any] | None = None
    for _ in range(4096):
        try:
            kind, payload, console, prefix = display_events.get_nowait()
        except queue.Empty:
            break
        if kind == 'progress':
            if progress_events is not None:
                progress_events.write(canonical_json(payload) + '\n')
                progress_events.flush()
            pending_progress = payload
        elif console is not None:
            if pending_progress is not None and progress is not None:
                progress.observe_yadof_snapshot(pending_progress)
                pending_progress = None
            if progress is None:
                console.write(f'{prefix}{payload}')
                console.flush()
            else:
                progress.write_above(f'{prefix}{payload}', console=console)
    if pending_progress is not None and progress is not None:
        progress.observe_yadof_snapshot(pending_progress)

def _execute_logged(command: Sequence[str], *, cwd: Path, attempt_root: Path, attempt: dict[str, Any], timeout_sec: int, label: str, stream_output: bool=False, progress: CellProgress | None=None) -> dict[str, Any]:
    from .planning import safe_id as _safe_id
    from .progress import CellProgress
    from .storage import canonical_json, file_sha256, utc_now, write_new_json
    sequence = len(attempt['commands']) + 1
    command_root = attempt_root / 'commands' / f'{sequence:04d}-{_safe_id(label)}'
    command_root.mkdir(parents=True, exist_ok=False)
    stdout_path = command_root / 'stdout.log'
    stderr_path = command_root / 'stderr.log'
    progress_path = command_root / PROGRESS_EVENTS_NAME
    started_path = command_root / 'command.started.json'
    finished_path = command_root / 'command.finished.json'
    metadata: dict[str, Any] = {'schema_version': SCHEMA_VERSION, 'sequence': sequence, 'label': label, 'command': list(command), 'cwd': str(cwd), 'started_utc': utc_now(), 'ended_utc': None, 'duration_sec': None, 'returncode': None, 'timed_out': False, 'stdout': str(stdout_path), 'stderr': str(stderr_path), 'progress_events': str(progress_path), 'stdout_sha256': None, 'stderr_sha256': None, 'progress_events_sha256': None}
    write_new_json(started_path, metadata)
    progress_events = progress_path.open('x', encoding='utf-8', newline='\n')
    progress_events.write(canonical_json({'schema_version': SCHEMA_VERSION, 'event': 'command-start', 'observed_utc': metadata['started_utc'], 'phase': label}) + '\n')
    progress_events.flush()
    if stream_output:
        message = f"[{label}] {' '.join((str(part) for part in command))}\n"
        if progress is None:
            sys.stdout.write(message)
            sys.stdout.flush()
        else:
            progress.write_above(message, console=sys.stdout)
    else:
        message = f'[{label}] started; log_dir={command_root.relative_to(attempt_root)}\n'
        if progress is None:
            sys.stderr.write(message)
            sys.stderr.flush()
        else:
            progress.write_above(message)
    started = time.perf_counter()
    creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) if os.name == 'nt' else 0
    child_environment = os.environ.copy()
    child_environment['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        process = subprocess.Popen(list(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags, env=child_environment)
    except BaseException:
        progress_events.close()
        raise
    assert process.stdout is not None and process.stderr is not None
    display_events: queue.Queue[tuple[str, Any, Any | None, str]] = queue.Queue()
    out_thread = threading.Thread(target=_stream_pipe, args=(process.stdout, stdout_path, sys.stdout if stream_output else None, f'[{label}:out] ', progress, display_events), daemon=True)
    err_thread = threading.Thread(target=_stream_pipe, args=(process.stderr, stderr_path, sys.stderr if stream_output else None, f'[{label}:err] ', progress, display_events), daemon=True)
    out_thread.start()
    err_thread.start()
    deadline = started + timeout_sec
    returncode: int | None = None
    while returncode is None:
        _render_stream_events(display_events, progress, progress_events)
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            metadata['timed_out'] = True
            process.kill()
            returncode = process.wait()
            break
        try:
            returncode = process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            continue
    out_thread.join()
    err_thread.join()
    _render_stream_events(display_events, progress, progress_events)
    metadata.update({'ended_utc': utc_now(), 'duration_sec': time.perf_counter() - started, 'returncode': returncode, 'stdout_sha256': file_sha256(stdout_path), 'stderr_sha256': file_sha256(stderr_path)})
    progress_events.write(canonical_json({'schema_version': SCHEMA_VERSION, 'event': 'command-end', 'observed_utc': metadata['ended_utc'], 'phase': label, 'returncode': returncode, 'timed_out': metadata['timed_out']}) + '\n')
    progress_events.flush()
    os.fsync(progress_events.fileno())
    progress_events.close()
    metadata['progress_events_sha256'] = file_sha256(progress_path)
    write_new_json(finished_path, metadata)
    attempt['commands'].append(str(finished_path))
    if not stream_output and (returncode != 0 or metadata['timed_out']):
        message = f"[{label}] failed; returncode={returncode}; timed_out={metadata['timed_out']}; metadata={finished_path}\n"
        if progress is None:
            sys.stderr.write(message)
            sys.stderr.flush()
        else:
            progress.write_above(message)
    return metadata

def _completed_generation_indices(workspace: Path) -> list[int]:
    from .results import generation_metadata as _generation_metadata
    from yadof.recorded_data import list_optimization_metadata
    metadata = _generation_metadata(list_optimization_metadata(workspace))
    return sorted({int(item.get('generation_index', -1)) for item in metadata})

def _has_completed_generation_prefix(workspace: Path, count: int) -> tuple[bool, list[int]]:
    indices = _completed_generation_indices(workspace)
    return (indices[:count] == list(range(count)), indices)

def _surrogate_has_been_used(workspace: Path) -> bool:
    from .results import generation_metadata as _generation_metadata
    from yadof.recorded_data import list_optimization_metadata
    return any((item.get('surrogate_used') is True for item in _generation_metadata(list_optimization_metadata(workspace))))

def _cell_command(spec: Mapping[str, Any], cell: Mapping[str, Any], workspace: Path) -> list[str]:
    python = str(spec['package']['python'])
    case = spec['cases'][cell['case']]
    if cell['kind'] == 'smoke':
        return [python, '-m', 'yadof', 'smoke-test', '--workspace', str(workspace), '--mode', str(case['mode']), '--real-task']
    return [python, '-m', 'yadof', 'run', '--workspace', str(workspace), '--generations', str(cell['generations']), '--start-generation', '0', '--mode', str(case['mode']), '--population-size', str(cell['population']), '--random-seed', str(cell['seed']), '--no-smoke-test', '--progress', '--fail-on-all-infinite']

def _seal_attempt(run_root: Path, state: dict[str, Any], cell_plan: Mapping[str, Any], attempt: dict[str, Any], *, status: str, include_paths: Sequence[str], error: str | None=None) -> None:
    from .state import save_state as _save_state
    from .storage import task_fingerprint, utc_now
    cell_state = state['cells'][cell_plan['cell_id']]
    workspace = Path(attempt['workspace'])
    fingerprint = task_fingerprint(workspace, include_paths) if attempt.get('input_fingerprint') is not None else None
    attempt['post_input_fingerprint'] = fingerprint
    attempt['status'] = status
    attempt['error'] = error
    attempt['sealed_utc'] = utc_now()
    cell_state['status'] = status
    event = 'cell-completed' if status == 'completed' else 'cell-failed'
    _save_state(run_root, state, event=event, cell_id=cell_plan['cell_id'], attempt=attempt['attempt'], error=error)

def _seal_interrupted_attempt(
    run_root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell_plan: Mapping[str, Any],
    cell_state: dict[str, Any],
) -> None:
    from .state import save_state
    from .storage import task_fingerprint, utc_now
    previous = cell_state['attempts'][-1]
    if previous.get('input_fingerprint') is not None and Path(previous['workspace']).is_dir():
        with contextlib.suppress(Exception):
            previous['post_input_fingerprint'] = task_fingerprint(Path(previous['workspace']), spec['cases'][cell_plan['case']]['baseline']['include_paths'])
    previous['status'] = 'failed'
    previous['error'] = 'runner stopped before the attempt was sealed'
    previous['sealed_utc'] = utc_now()
    cell_state['status'] = 'failed'
    save_state(run_root, state, event='interrupted-attempt-sealed', cell_id=cell_plan['cell_id'])

def _run_one_cell(config: Mapping[str, Any], paths: Paths, run_root: Path, spec: Mapping[str, Any], state: dict[str, Any], cell_plan: Mapping[str, Any], *, stream_subprocess_output: bool=False, progress: CellProgress | None=None) -> bool:
    from .planning import cost_view_command as _cost_view_command, postprocess_command as _postprocess_command
    from .progress import CellProgress
    from .state import materialize_attempt_inputs as _materialize_attempt_inputs, prepare_attempt as _prepare_attempt, save_state as _save_state
    from .storage import utc_now
    cell_state = state['cells'][cell_plan['cell_id']]
    if cell_state['status'] == 'completed':
        return True
    if cell_state['status'] == 'running':
        _seal_interrupted_attempt(run_root, spec, state, cell_plan, cell_state)
    try:
        attempt_root, attempt = _prepare_attempt(config, paths, run_root, spec, cell_plan, cell_state)
        _save_state(run_root, state, event='cell-attempt-prepared', cell_id=cell_plan['cell_id'], attempt=attempt['attempt'], replacement_for=attempt['replacement_for'])
        include_paths = spec['cases'][cell_plan['case']]['baseline']['include_paths']
        workspace = Path(attempt['workspace'])
        timeout = int(spec['runner']['command_timeout_sec'])
        if progress is not None:
            progress.set_phase('init')
        initialize = _execute_logged([spec['package']['python'], '-m', 'yadof', 'init', str(workspace)], cwd=paths.root, attempt_root=attempt_root, attempt=attempt, timeout_sec=min(timeout, 300), label='init', stream_output=stream_subprocess_output, progress=progress)
        _save_state(run_root, state)
        if initialize['returncode'] != 0 or initialize['timed_out']:
            _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error='yadof init failed')
            return False
        _materialize_attempt_inputs(paths, run_root, spec, cell_plan, attempt_root, attempt)
        _save_state(run_root, state, event='cell-inputs-materialized', cell_id=cell_plan['cell_id'], attempt=attempt['attempt'], input_fingerprint=attempt['input_fingerprint'])
        if progress is not None:
            progress.set_phase('check')
        check = _execute_logged([spec['package']['python'], '-m', 'yadof', 'check', '--workspace', str(workspace)], cwd=paths.root, attempt_root=attempt_root, attempt=attempt, timeout_sec=min(timeout, 300), label='check', stream_output=stream_subprocess_output, progress=progress)
        _save_state(run_root, state)
        if check['returncode'] != 0 or check['timed_out']:
            _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error='yadof check failed')
            return False
        command = _cell_command(spec, cell_plan, workspace)
        if progress is not None:
            progress.set_phase('smoke' if cell_plan['kind'] == 'smoke' else 'optimization')
        result = _execute_logged(command, cwd=paths.root, attempt_root=attempt_root, attempt=attempt, timeout_sec=timeout, label='smoke' if cell_plan['kind'] == 'smoke' else 'optimize', stream_output=stream_subprocess_output, progress=progress)
        _save_state(run_root, state)
        if result['returncode'] != 0 or result['timed_out']:
            error = 'command timed out' if result['timed_out'] else f"command exited {result['returncode']}"
            _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error=error)
            return False
        generations_ok, observed_indices = _has_completed_generation_prefix(workspace, int(cell_plan['generations'])) if cell_plan['kind'] == 'measured' else (True, [])
        if not generations_ok:
            _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error=f'yadof command returned success without the expected complete generation metadata prefix; observed {observed_indices}')
            return False
        if cell_plan['kind'] == 'measured' and spec['arms'][cell_plan['arm']]['surrogate'] and (int(cell_plan['max_generations']) > int(cell_plan['generations'])):
            if not _surrogate_has_been_used(workspace):
                extra = int(cell_plan['max_generations']) - int(cell_plan['generations'])
                extension = [spec['package']['python'], '-m', 'yadof', 'run', '--workspace', str(workspace), '--generations', str(extra), '--start-generation', str(cell_plan['generations']), '--mode', str(spec['cases'][cell_plan['case']]['mode']), '--population-size', str(cell_plan['population']), '--random-seed', str(cell_plan['seed']), '--no-smoke-test', '--progress', '--fail-on-all-infinite']
                if progress is not None:
                    progress.extend_current(extra * int(cell_plan['population']))
                    progress.set_phase('checkpoint-extension')
                extension_result = _execute_logged(extension, cwd=paths.root, attempt_root=attempt_root, attempt=attempt, timeout_sec=timeout, label='optional-checkpoint-extension', stream_output=stream_subprocess_output, progress=progress)
                _save_state(run_root, state)
                if extension_result['returncode'] != 0 or extension_result['timed_out']:
                    _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error='optional checkpoint extension failed')
                    return False
                extension_ok, extension_indices = _has_completed_generation_prefix(workspace, int(cell_plan['max_generations']))
                if not extension_ok:
                    _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error=f'checkpoint extension returned success without the expected complete generation metadata prefix; observed {extension_indices}')
                    return False
        if cell_plan['kind'] == 'measured':
            visualization_output_dir = Path(attempt['visualization_output_dir'])
            visualization_output_dir.mkdir(parents=True, exist_ok=True)
            visualization_file_prefix = str(attempt['visualization_file_prefix'])
            if progress is not None:
                progress.set_phase('postprocess')
            postprocess = _execute_logged(_postprocess_command(spec['package']['python'], workspace, visualization_output_dir, visualization_file_prefix), cwd=paths.root, attempt_root=attempt_root, attempt=attempt, timeout_sec=timeout, label='postprocess', stream_output=stream_subprocess_output, progress=progress)
            _save_state(run_root, state)
            if postprocess['returncode'] != 0 or postprocess['timed_out']:
                _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error='baseline postprocess failed')
                return False
            cost_output = Path(attempt['cost_visualization_output'])
            cost_output.parent.mkdir(parents=True, exist_ok=True)
            if cost_output.exists():
                _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error=f'visualization output already exists: {cost_output.name}')
                return False
            if progress is not None:
                progress.set_phase('view-cost')
            cost_view = _execute_logged(_cost_view_command(spec['package']['python'], workspace, cost_output), cwd=paths.root, attempt_root=attempt_root, attempt=attempt, timeout_sec=min(timeout, 600), label='view-cost', stream_output=stream_subprocess_output, progress=progress)
            _save_state(run_root, state)
            if cost_view['returncode'] != 0 or cost_view['timed_out']:
                _seal_attempt(run_root, state, cell_plan, attempt, status='failed', include_paths=include_paths, error='yadof view cost failed')
                return False
        _seal_attempt(run_root, state, cell_plan, attempt, status='completed', include_paths=include_paths)
        return True
    except Exception as exc:
        if cell_state.get('attempts'):
            attempt = cell_state['attempts'][-1]
            if attempt.get('status') not in TERMINAL_CELL_STATES:
                attempt['status'] = 'failed'
                attempt['error'] = str(exc)
                attempt['sealed_utc'] = utc_now()
        cell_state['status'] = 'failed'
        _save_state(run_root, state, event='cell-exception', cell_id=cell_plan['cell_id'], error=str(exc))
        return False

def execute_run(config: Mapping[str, Any], paths: Paths, run_id: str, *, fail_fast_override: bool | None=None, stream_subprocess_output: bool=False) -> dict[str, Any]:
    from .progress import CellProgress
    from .state import save_state as _save_state, load_run
    run_root, spec, state = load_run(paths, run_id)
    fail_fast = bool(spec['runner']['fail_fast']) if fail_fast_override is None else fail_fast_override
    state['status'] = 'running'
    _save_state(run_root, state, event='run-started-or-resumed', fail_fast=fail_fast)
    stop = False
    cells = spec['plan']['cells']
    completed_at_start = sum((state['cells'][cell['cell_id']]['status'] == 'completed' for cell in cells))
    progress = CellProgress(len(cells), completed=completed_at_start)
    progress.start()
    try:
        for cell_plan in cells:
            cell_state = state['cells'][cell_plan['cell_id']]
            if cell_state['status'] == 'completed':
                continue
            if stop:
                cell_state['status'] = 'skipped'
                _save_state(run_root, state, event='cell-skipped-fail-fast', cell_id=cell_plan['cell_id'])
                progress.advance('skipped')
                continue
            progress.start_cell(cell_plan)
            progress.write_above(f"[cell] {cell_plan['cell_id']} started\n")
            ok = _run_one_cell(config, paths, run_root, spec, state, cell_plan, stream_subprocess_output=stream_subprocess_output, progress=progress)
            status = str(state['cells'][cell_plan['cell_id']]['status'])
            progress.write_above(f"[cell] {cell_plan['cell_id']} {status}\n")
            progress.advance(status)
            if not ok and fail_fast:
                stop = True
    finally:
        progress.finish()
    statuses = [cell['status'] for cell in state['cells'].values()]
    if all((status == 'completed' for status in statuses)):
        state['status'] = 'completed'
    elif any((status == 'failed' for status in statuses)):
        state['status'] = 'incomplete'
    else:
        state['status'] = 'incomplete'
    _save_state(run_root, state, event='run-finished', status=state['status'])
    return state
