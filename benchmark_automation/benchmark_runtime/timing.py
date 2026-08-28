"""Timing services for benchmark automation."""
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

def _parse_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed.astimezone(dt.UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.UTC)

def _format_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

def _attempt_duration_sec(attempt: Mapping[str, Any]) -> float | None:
    started = _parse_utc(attempt.get('created_utc'))
    ended = _parse_utc(attempt.get('sealed_utc'))
    if started is None or ended is None or ended < started:
        return None
    return (ended - started).total_seconds()

def _timing_signature_payload(spec: Mapping[str, Any], cell: Mapping[str, Any], *, exact: bool) -> dict[str, Any]:
    """Return stable operational attributes that make two cell timings comparable."""
    case_id = cell.get('case')
    arm_id = cell.get('arm')
    case = spec.get('cases', {}).get(case_id, {})
    baseline = case.get('baseline', {})
    starting_evidence = case.get('starting_evidence', {})
    arm = spec.get('arms', {}).get(arm_id, {}) if arm_id is not None else {}
    payload: dict[str, Any] = {'kind': cell.get('kind'), 'case': case_id, 'arm': arm_id, 'budget': {key: int(cell.get(key, 0) or 0) for key in ('population', 'generations', 'max_generations', 'planned_attempted_evaluations')}, 'case_contract': {'mode': case.get('mode'), 'max_workers': int(case.get('max_workers', 1) or 1), 'rawdata_shapes': case.get('rawdata_shapes', {}), 'baseline_id': baseline.get('baseline_id'), 'task_fingerprint': baseline.get('actual_task_fingerprint'), 'starting_evidence_fingerprint': starting_evidence.get('fingerprint'), 'resource': case.get('resolved_resource') or case.get('resource', {})}, 'arm_contract': {'constructed_type': arm.get('constructed_type'), 'surrogate': bool(arm.get('surrogate', False)), 'config_overrides': arm.get('config_overrides', {})} if arm_id is not None else None, 'runner_overrides': spec.get('runner', {}).get('measured_config_overrides', {}), 'host': {'node': spec.get('host', {}).get('node'), 'platform': spec.get('host', {}).get('platform')}}
    if exact:
        package = spec.get('package', {})
        payload['implementation_fingerprints'] = {'package': {key: package.get(key) for key in ('version', 'module_sha256', 'distribution_record_sha256', 'python')}, 'arm_template_sha256': arm.get('sha256') if arm_id is not None else None, 'automation': {name: item.get('sha256') for name, item in spec.get('automation', {}).items() if isinstance(item, Mapping)}}
    return payload

def _timing_signatures(spec: Mapping[str, Any], cell: Mapping[str, Any]) -> tuple[str, str]:
    from .storage import object_sha256
    return (object_sha256(_timing_signature_payload(spec, cell, exact=True)), object_sha256(_timing_signature_payload(spec, cell, exact=False)))

def _snapshot_cross_run_timing(paths: Paths, spec: Mapping[str, Any], *, current_run_id: str) -> dict[str, Any]:
    """Freeze a bounded, shallow timing sample from earlier completed runs."""
    from .state import load_run
    from .storage import utc_now
    target_signatures = {_timing_signatures(spec, cell) for cell in spec.get('plan', {}).get('cells', [])}
    target_exact = {exact for exact, _compatible in target_signatures}
    target_compatible = {compatible for _exact, compatible in target_signatures}
    try:
        candidates = sorted((path for path in paths.runs.iterdir() if path.is_dir() and path.name != current_run_id), key=lambda path: path.name, reverse=True)[:TIMING_HISTORY_RUN_LIMIT]
    except OSError:
        candidates = []
    observations: list[dict[str, Any]] = []
    source_run_ids: list[str] = []
    readable_runs = 0
    skipped_runs = 0
    for candidate in candidates:
        try:
            _prior_root, prior_spec, prior_state = load_run(paths, candidate.name)
        except (BenchmarkError, OSError):
            skipped_runs += 1
            continue
        readable_runs += 1
        matched_source = False
        plan_by_cell = {str(item.get('cell_id')): item for item in prior_spec.get('plan', {}).get('cells', [])}
        for cell_id, cell_state in prior_state.get('cells', {}).items():
            if cell_state.get('status') != 'completed':
                continue
            attempts = cell_state.get('attempts') or []
            plan = plan_by_cell.get(str(cell_id))
            if not attempts or not isinstance(plan, Mapping):
                continue
            duration = _attempt_duration_sec(attempts[-1])
            planned = int(plan.get('planned_attempted_evaluations', 0) or 0)
            if duration is None or duration <= 0.0 or planned <= 0:
                continue
            exact_signature, compatible_signature = _timing_signatures(prior_spec, plan)
            if exact_signature not in target_exact and compatible_signature not in target_compatible:
                continue
            observations.append({'source_run_id': candidate.name, 'source_created_utc': prior_state.get('created_utc'), 'source_cell_id': cell_id, 'sealed_utc': attempts[-1].get('sealed_utc'), 'kind': plan.get('kind'), 'case': plan.get('case'), 'arm': plan.get('arm'), 'planned': planned, 'duration_sec': duration, 'exact_signature': exact_signature, 'compatible_signature': compatible_signature})
            matched_source = True
        if matched_source:
            source_run_ids.append(candidate.name)
    observations.sort(key=lambda row: str(row.get('sealed_utc') or row.get('source_created_utc') or ''), reverse=True)
    observations = observations[:TIMING_HISTORY_OBSERVATION_LIMIT]
    retained_source_ids = {str(row.get('source_run_id')) for row in observations}
    source_run_ids = [run_id for run_id in source_run_ids if run_id in retained_source_ids]
    return {'schema_version': SCHEMA_VERSION, 'created_utc': utc_now(), 'policy': {'scan': 'immediate run directories only', 'run_limit': TIMING_HISTORY_RUN_LIMIT, 'observation_limit': TIMING_HISTORY_OBSERVATION_LIMIT, 'statistic': 'median'}, 'scanned_run_count': len(candidates), 'readable_run_count': readable_runs, 'source_run_count': len(source_run_ids), 'source_run_ids': source_run_ids, 'skipped_run_count': skipped_runs, 'observation_count': len(observations), 'observations': observations, 'target_signature_count': len(target_signatures)}

def _load_timing_history(run_root: Path | None) -> dict[str, Any]:
    from .storage import read_json
    if run_root is None:
        return {}
    path = run_root / TIMING_HISTORY_NAME
    if not path.is_file():
        return {}
    try:
        payload = read_json(path)
    except (BenchmarkError, OSError):
        return {}
    return payload if isinstance(payload.get('observations', []), list) else {}

def _duration_observations(state: Mapping[str, Any], plan_by_cell: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for cell_id, cell in state.get('cells', {}).items():
        if cell.get('status') != 'completed':
            continue
        attempts = cell.get('attempts') or []
        if not attempts:
            continue
        duration = _attempt_duration_sec(attempts[-1])
        plan = plan_by_cell.get(str(cell_id), {})
        planned = int(plan.get('planned_attempted_evaluations', 0) or 0)
        if duration is None or duration <= 0.0 or planned <= 0:
            continue
        observations.append({'case': cell.get('case'), 'arm': cell.get('arm'), 'planned': planned, 'duration_sec': duration})
    return observations

def _cell_duration_estimate(cell: Mapping[str, Any], spec: Mapping[str, Any], observations: Sequence[Mapping[str, Any]], history_observations: Sequence[Mapping[str, Any]]=()) -> tuple[float | None, str, int, float | None]:
    planned = int(cell.get('planned_attempted_evaluations', 0) or 0)
    if planned <= 0:
        return (None, 'unavailable', 0, None)
    case_id = cell.get('case')
    arm_id = cell.get('arm')
    exact_signature, compatible_signature = _timing_signatures(spec, cell)
    cohorts = (('prior-run-exact-cell', [row for row in history_observations if row.get('exact_signature') == exact_signature]), ('same-case-arm', [row for row in observations if row.get('case') == case_id and row.get('arm') == arm_id]), ('prior-run-compatible-cell', [row for row in history_observations if row.get('compatible_signature') == compatible_signature]), ('same-arm', [row for row in observations if arm_id is not None and row.get('arm') == arm_id]))
    for basis, rows in cohorts:
        scaled = [float(row['duration_sec']) * planned / int(row['planned']) for row in rows if int(row.get('planned', 0) or 0) > 0 and float(row.get('duration_sec', 0.0) or 0.0) > 0.0]
        if scaled:
            median = statistics.median(scaled)
            absolute_deviations = [abs(value - median) for value in scaled]
            relative_mad = statistics.median(absolute_deviations) / median if median > 0.0 else None
            return (median, basis, len(scaled), relative_mad)
    case = spec.get('cases', {}).get(case_id, {})
    observed_eval_sec = float(case.get('observed_eval_sec', 0.0) or 0.0)
    workers = max(1, int(case.get('max_workers', 1) or 1))
    if observed_eval_sec > 0.0:
        return (observed_eval_sec * planned / workers, 'declared-evaluation-lower-bound', 0, None)
    plan = spec.get('plan', {})
    total_planned = sum((int(item.get('planned_attempted_evaluations', 0) or 0) for item in plan.get('cells', [])))
    lower_bound = float(plan.get('estimates', {}).get('evaluation_wall_lower_bound_sec', 0.0) or 0.0)
    if lower_bound > 0.0 and total_planned > 0:
        return (lower_bound * planned / total_planned, 'plan-average-lower-bound', 0, None)
    return (None, 'unavailable', 0, None)

def _tail_yadof_progress(path: Path, *, limit_bytes: int=262144) -> dict[str, Any] | None:
    from .progress import parse_yadof_progress as _parse_yadof_progress
    if not path.is_file():
        return None
    try:
        with path.open('rb') as stream:
            size = path.stat().st_size
            stream.seek(max(0, size - limit_bytes))
            text = stream.read().decode('utf-8', errors='replace')
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        parsed = _parse_yadof_progress(line)
        if parsed is not None:
            return parsed
    return None

def _tail_progress_events(path: Path, *, limit_bytes: int=PROGRESS_EVENT_TAIL_BYTES) -> list[dict[str, Any]]:
    """Read a bounded suffix of the append-only command progress event stream."""
    if not path.is_file():
        return []
    try:
        with path.open('rb') as stream:
            size = path.stat().st_size
            offset = max(0, size - limit_bytes)
            stream.seek(offset)
            text = stream.read().decode('utf-8', errors='replace')
    except OSError:
        return []
    lines = text.splitlines()
    if offset > 0 and lines:
        lines = lines[1:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get('event'), str):
            events.append(event)
    return events

def _active_command(attempt: Mapping[str, Any]) -> dict[str, Any] | None:
    from .storage import read_json
    workspace_value = attempt.get('workspace')
    if not isinstance(workspace_value, str):
        return None
    commands_root = Path(workspace_value).parent / 'commands'
    try:
        command_roots = sorted((path for path in commands_root.iterdir() if path.is_dir()), key=lambda path: path.name)
    except OSError:
        return None
    if not command_roots:
        return None
    command_root = command_roots[-1]
    finished_path = command_root / 'command.finished.json'
    started_path = command_root / 'command.started.json'
    metadata_path = finished_path if finished_path.is_file() else started_path
    if not metadata_path.is_file():
        return None
    try:
        metadata = read_json(metadata_path)
    except (BenchmarkError, OSError):
        return None
    stderr_value = metadata.get('stderr')
    stderr_path = Path(stderr_value) if isinstance(stderr_value, str) else command_root / 'stderr.log'
    stdout_value = metadata.get('stdout')
    stdout_path = Path(stdout_value) if isinstance(stdout_value, str) else command_root / 'stdout.log'
    progress_value = metadata.get('progress_events')
    progress_path = Path(progress_value) if isinstance(progress_value, str) else command_root / PROGRESS_EVENTS_NAME
    progress_events = _tail_progress_events(progress_path)
    progress_snapshots = [event for event in progress_events if event.get('event') == 'progress']
    progress = progress_snapshots[-1] if progress_snapshots else _tail_yadof_progress(stderr_path)
    activity_times = [_parse_utc(metadata.get('started_utc')), _parse_utc(metadata.get('ended_utc'))]
    activity_times.extend((_parse_utc(event.get('observed_utc')) for event in progress_events))
    for candidate in (stderr_path, stdout_path, progress_path):
        if candidate.is_file():
            with contextlib.suppress(OSError):
                activity_times.append(dt.datetime.fromtimestamp(candidate.stat().st_mtime, dt.UTC))
    activity = max((value for value in activity_times if value is not None), default=None)
    return {'label': metadata.get('label'), 'started_utc': metadata.get('started_utc'), 'finished': finished_path.is_file(), 'progress': progress, 'progress_events': progress_events, 'last_activity': activity}

def _generation_phase_estimate(command: Mapping[str, Any], plan: Mapping[str, Any], checked: dt.datetime) -> dict[str, Any] | None:
    """Forecast the current optimization tail from timestamped generation boundaries."""
    started = _parse_utc(command.get('started_utc'))
    if started is None:
        return None
    progress_events = [event for event in command.get('progress_events', []) if isinstance(event, Mapping) and event.get('event') == 'progress' and isinstance(event.get('generation'), int) and (_parse_utc(event.get('observed_utc')) is not None)]
    if not progress_events:
        return None
    first_generation = min((int(event['generation']) for event in progress_events))
    configured_generations = max(0, int(plan.get('generations', 0) or 0))
    maximum_generations = max(configured_generations, int(plan.get('max_generations', 0) or 0))
    label = str(command.get('label') or '')
    if 'extend' not in label and first_generation != 0:
        return None
    target_generation = maximum_generations if 'extend' in label or first_generation >= configured_generations else configured_generations
    if target_generation <= first_generation:
        return None
    completion_times: dict[int, dt.datetime] = {}
    for event in progress_events:
        generation = int(event['generation'])
        finished = int(event.get('finished', 0) or 0)
        total = max(1, int(event.get('total', 1) or 1))
        observed = _parse_utc(event.get('observed_utc'))
        if finished >= total and observed is not None:
            completion_times.setdefault(generation, observed)
    durations: list[float] = []
    boundaries: list[dt.datetime] = [started]
    generation = first_generation
    while generation < target_generation and generation in completion_times:
        ended = completion_times[generation]
        previous = boundaries[-1]
        if ended < previous:
            break
        durations.append(max(0.001, (ended - previous).total_seconds()))
        boundaries.append(ended)
        generation += 1
    if len(durations) < 3 or generation >= target_generation:
        return None
    recent = durations[-6:]
    slopes = [(recent[right] - recent[left]) / (right - left) for left in range(len(recent)) for right in range(left + 1, len(recent))]
    slope = max(0.0, statistics.median(slopes)) if slopes else 0.0
    intercept = statistics.median((value - slope * index for index, value in enumerate(recent)))
    completed_in_command = len(durations)
    remaining_generations = target_generation - generation
    current_elapsed = max(0.0, (checked - boundaries[-1]).total_seconds())
    forecast: list[float] = []
    for offset in range(remaining_generations):
        relative_index = len(recent) + offset
        forecast.append(max(1.0, intercept + slope * relative_index))
    if not forecast:
        return None
    remaining = max(0.0, forecast[0] - current_elapsed) + sum(forecast[1:])
    return {'remaining_sec': remaining, 'completed_generations': generation, 'target_generations': target_generation, 'sample_count': completed_in_command, 'recent_generation_sec': [round(value, 3) for value in recent], 'trend_sec_per_generation': round(slope, 3), 'current_generation_elapsed_sec': round(current_elapsed, 3)}

def _estimate_confidence(
    *,
    terminal: bool,
    remaining: float | None,
    active_summary: Mapping[str, Any] | None,
    bases: set[str],
    minimum_samples: Mapping[str, int],
    maximum_spreads: Mapping[str, float | None],
) -> str:
    if terminal:
        return 'high'
    if remaining is None:
        return 'unavailable'
    if bases <= {'same-case-arm'} and active_summary is not None and active_summary['completed_evaluations'] > 0:
        return 'high'
    if bases <= {'prior-run-exact-cell', 'live-generation-trend'} and all(minimum_samples.get(basis, 0) >= 3 for basis in bases):
        return 'high'
    supported = {'prior-run-exact-cell', 'prior-run-compatible-cell', 'same-case-arm', 'live-generation-trend'}
    stable = all(minimum_samples.get(basis, 0) >= 2 and (maximum_spreads.get(basis) is None or float(maximum_spreads[basis]) <= 0.25) for basis in bases)
    return 'medium' if bases <= supported and stable else 'low'


def _remaining_duration(
    state: Mapping[str, Any],
    estimate_available: bool,
    pending_remaining: float,
    active_remaining: float,
) -> tuple[bool, float | None]:
    terminal = not any(str(cell.get('status')) in {'pending', 'running'} for cell in state.get('cells', {}).values())
    if terminal:
        return True, 0.0
    if estimate_available:
        return False, pending_remaining + active_remaining
    return False, None


def estimate_run_timing(spec: Mapping[str, Any], state: Mapping[str, Any], *, run_root: Path | None=None, timing_history: Mapping[str, Any] | None=None, now: dt.datetime | None=None) -> dict[str, Any]:
    """Estimate sequential completion from matched cells and timestamped phase evidence."""
    from .storage import json_safe as _json_safe
    checked = dt.datetime.now(dt.UTC) if now is None else now.astimezone(dt.UTC)
    plan_by_cell = {str(cell['cell_id']): cell for cell in spec.get('plan', {}).get('cells', [])}
    observations = _duration_observations(state, plan_by_cell)
    history_payload = dict(timing_history) if timing_history is not None else _load_timing_history(run_root)
    history_observations = [row for row in history_payload.get('observations', []) if isinstance(row, Mapping)]
    basis_counts: dict[str, int] = defaultdict(int)
    basis_samples: dict[str, list[int]] = defaultdict(list)
    basis_spreads: dict[str, list[float]] = defaultdict(list)
    pending_remaining = 0.0
    estimate_available = True
    active_summary: dict[str, Any] | None = None
    active_remaining = 0.0
    for cell_id, cell_state in state.get('cells', {}).items():
        status = str(cell_state.get('status', 'unknown'))
        if status not in {'pending', 'running'}:
            continue
        plan = plan_by_cell.get(str(cell_id), {})
        full_duration, basis, sample_count, relative_mad = _cell_duration_estimate(plan, spec, observations, history_observations)
        if status == 'pending':
            basis_counts[basis] += 1
            basis_samples[basis].append(sample_count)
            if relative_mad is not None:
                basis_spreads[basis].append(relative_mad)
            if full_duration is None:
                estimate_available = False
            else:
                pending_remaining += full_duration
            continue
        attempts = cell_state.get('attempts') or []
        attempt = attempts[-1] if attempts else {}
        attempt_started = _parse_utc(attempt.get('created_utc'))
        attempt_elapsed = max(0.0, (checked - attempt_started).total_seconds()) if attempt_started is not None else 0.0
        candidates: list[dict[str, Any]] = []
        if full_duration is not None:
            candidates.append({'remaining_sec': max(60.0, full_duration - attempt_elapsed), 'basis': basis, 'sample_count': sample_count, 'relative_mad': relative_mad})
        command = _active_command(attempt)
        planned = int(plan.get('planned_attempted_evaluations', 0) or 0)
        completed = 0
        phase = 'preparing'
        last_activity: dt.datetime | None = attempt_started
        generation_timing: dict[str, Any] | None = None
        if command is not None:
            phase = str(command.get('label') or phase)
            last_activity = command.get('last_activity') or last_activity
            snapshot = command.get('progress')
            command_started = _parse_utc(command.get('started_utc'))
            if isinstance(snapshot, Mapping):
                completed = min(planned, int(snapshot.get('absolute_finished', 0) or 0))
                generation = snapshot.get('generation')
                phase = 'smoke' if generation is None else f'generation-{int(generation) + 1}'
            generation_timing = _generation_phase_estimate(command, plan, checked)
            if generation_timing is not None:
                candidates.append({'remaining_sec': max(60.0, float(generation_timing['remaining_sec'])), 'basis': 'live-generation-trend', 'sample_count': int(generation_timing['sample_count']), 'relative_mad': None})
            elif isinstance(snapshot, Mapping) and completed > 0 and (planned > completed) and (command_started is not None):
                command_elapsed = max(0.0, (checked - command_started).total_seconds())
                live_remaining = command_elapsed * (planned - completed) / completed
                candidates.append({'remaining_sec': max(60.0, live_remaining), 'basis': 'live-linear-progress', 'sample_count': 1, 'relative_mad': None})
        inactive_sec = max(0.0, (checked - last_activity).total_seconds()) if last_activity is not None else None
        if candidates:
            chosen = max(candidates, key=lambda item: float(item['remaining_sec']))
            chosen_remaining = float(chosen['remaining_sec'])
            active_remaining += chosen_remaining
            chosen_basis = str(chosen['basis'])
            chosen_sample_count = int(chosen['sample_count'])
            chosen_relative_mad = chosen.get('relative_mad')
            basis_counts[chosen_basis] += 1
            basis_samples[chosen_basis].append(chosen_sample_count)
            if isinstance(chosen_relative_mad, (int, float)):
                basis_spreads[chosen_basis].append(float(chosen_relative_mad))
        else:
            estimate_available = False
            chosen_remaining = 0.0
            chosen_basis = 'unavailable'
            chosen_sample_count = 0
            chosen_relative_mad = None
            basis_counts[chosen_basis] += 1
            basis_samples[chosen_basis].append(0)
        active_summary = {'cell_id': cell_id, 'phase': phase, 'completed_evaluations': completed, 'planned_evaluations': planned, 'progress_percent': round(100.0 * completed / planned, 1) if planned > 0 else None, 'attempt_elapsed_sec': round(attempt_elapsed), 'inactive_sec': round(inactive_sec) if inactive_sec is not None else None, 'estimated_remaining_sec': round(chosen_remaining), 'estimate_basis': chosen_basis, 'basis_sample_count': chosen_sample_count, 'basis_relative_mad': round(float(chosen_relative_mad), 4) if isinstance(chosen_relative_mad, (int, float)) else None, 'generation_timing': generation_timing}
    terminal, remaining = _remaining_duration(
        state, estimate_available, pending_remaining, active_remaining
    )
    bases = set(basis_counts)
    minimum_samples = {basis: min(samples) if samples else 0 for basis, samples in basis_samples.items()}
    maximum_spreads = {basis: max(spreads) if spreads else None for basis, spreads in basis_spreads.items()}
    confidence = _estimate_confidence(
        terminal=terminal,
        remaining=remaining,
        active_summary=active_summary,
        bases=bases,
        minimum_samples=minimum_samples,
        maximum_spreads=maximum_spreads,
    )
    created = _parse_utc(state.get('created_utc'))
    elapsed = max(0.0, (checked - created).total_seconds()) if created is not None else None
    remaining_sec = round(remaining) if remaining is not None else None
    return _json_safe({'checked_utc': _format_utc(checked), 'started_utc': state.get('created_utc'), 'elapsed_sec': round(elapsed) if elapsed is not None else None, 'active_cell': active_summary, 'estimated_remaining_sec': remaining_sec, 'estimated_completion_utc': _format_utc(checked + dt.timedelta(seconds=remaining_sec)) if remaining_sec is not None else None, 'estimate_confidence': confidence, 'estimate_basis': dict(sorted(basis_counts.items())), 'estimate_support': {basis: {'minimum_sample_count': minimum_samples.get(basis, 0), 'maximum_relative_mad': round(float(maximum_spreads[basis]), 4) if maximum_spreads.get(basis) is not None else None} for basis in sorted(basis_counts)}, 'historical_observation_count': len(history_observations), 'estimate_note': 'Best-effort wall-clock estimate. It prefers matched prior-run or same-arm wall times and can raise an active-cell estimate from timestamped generation intervals; declared evaluation estimates remain lower bounds.'})

def summarize_run_state(run_root: Path, run_id: str, state: Mapping[str, Any], *, timing: Mapping[str, Any] | None=None) -> dict[str, Any]:
    """Return current cell status and only actionable attempt failures."""
    from .storage import json_safe as _json_safe
    by_status: dict[str, int] = defaultdict(int)
    attention: list[dict[str, Any]] = []
    cells = state.get('cells', {})
    for cell_id, cell in cells.items():
        status = str(cell.get('status', 'unknown'))
        by_status[status] += 1
        if status == 'completed':
            continue
        attempts = cell.get('attempts') or []
        latest = attempts[-1] if attempts else {}
        item: dict[str, Any] = {'cell_id': cell_id, 'status': status, 'error': latest.get('error'), 'attempt': latest.get('attempt')}
        commands = latest.get('commands') or []
        if commands:
            item['latest_command_metadata'] = commands[-1]
        attention.append(item)
    state_status = str(state.get('status', 'unknown'))
    runs_dir = run_root.resolve().parent
    next_command = ['--runs-dir', str(runs_dir), 'collect', '--run-id', run_id] if state_status == 'completed' else ['--runs-dir', str(runs_dir), 'resume', '--run-id', run_id]
    return _json_safe({'schema_version': state.get('schema_version', SCHEMA_VERSION), 'view': 'run-summary', 'run_id': run_id, 'runs_dir': str(runs_dir), 'run_root': str(run_root.resolve()), 'execution_state': state_status, 'updated_utc': state.get('updated_utc'), 'cells': {'total': len(cells), 'by_status': dict(sorted(by_status.items()))}, 'timing': timing, 'attention': attention, 'run_state': str(run_root / 'run_state.json'), 'next_command': next_command})


snapshot_cross_run_timing = _snapshot_cross_run_timing
