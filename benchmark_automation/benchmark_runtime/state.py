"""State services for benchmark automation."""
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

def _initial_state(run_id: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    from .storage import utc_now
    now = utc_now()
    cells = {cell['cell_id']: {'status': 'pending', 'kind': cell['kind'], 'case': cell['case'], 'arm': cell['arm'], 'seed': cell['seed'], 'attempts': []} for cell in spec['plan']['cells']}
    return {'schema_version': SCHEMA_VERSION, 'run_id': run_id, 'spec_sha256': spec['spec_sha256'], 'status': 'pending', 'created_utc': now, 'updated_utc': now, 'cells': cells, 'events': [{'at': now, 'event': 'run-created'}]}

def _copy_execution_snapshot(run_root: Path, spec: Mapping[str, Any]) -> None:
    from .storage import resolve_inside
    source = Path(__file__).resolve().parent
    destination = resolve_inside(
        run_root,
        spec.get('automation', {}).get('execution_snapshot', 'inputs/execution/benchmark_runtime'),
        label='execution snapshot',
    )
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

def _copy_strategy_snapshots(run_root: Path, spec: Mapping[str, Any]) -> None:
    from .storage import resolve_inside
    for arm_id, arm in spec.get('arms', {}).items():
        if arm.get('template'):
            pairs = [(arm['source_template'], arm['template'])]
        else:
            pairs = [
                (item['source_path'], item['path'])
                for item in arm.get('case_strategy_templates', {}).values()
            ]
        for source_value, target_value in pairs:
            target = resolve_inside(run_root, target_value, label=f'arm {arm_id} strategy snapshot')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(source_value), target)

def _copy_history_snapshots(run_root: Path, spec: Mapping[str, Any]) -> None:
    from .storage import resolve_inside
    for case_id, case in spec.get('cases', {}).items():
        evidence = case.get('starting_evidence', {})
        if evidence.get('policy') != 'snapshot':
            continue
        target = resolve_inside(run_root, evidence['snapshot'], label=f'case {case_id} history snapshot')
        shutil.copytree(Path(evidence['source_snapshot']), target)

def create_run(paths: Paths, spec: Mapping[str, Any], *, run_id: str | None=None) -> tuple[str, Path]:
    from .planning import safe_id as _safe_id, make_run_id
    from .storage import atomic_write_json, resolve_inside, write_new_json
    from .timing import snapshot_cross_run_timing as _snapshot_cross_run_timing
    chosen = _safe_id(run_id) if run_id else make_run_id(spec, spec.get('label'))
    run_root = resolve_inside(paths.runs, chosen, label='run_id')
    if run_root.exists():
        raise BenchmarkError(f'run already exists: {chosen}')
    run_root.mkdir(parents=True)
    try:
        for case_id, case in spec['cases'].items():
            baseline = case['baseline']
            snapshot = resolve_inside(run_root, baseline['snapshot_workspace'], label=f'case {case_id} baseline snapshot')
            snapshot.mkdir(parents=True)
            _copy_declared_inputs(Path(baseline['source_workspace']), snapshot, baseline['include_paths'])
        _copy_execution_snapshot(run_root, spec)
        _copy_strategy_snapshots(run_root, spec)
        _copy_history_snapshots(run_root, spec)
        write_new_json(run_root / 'run_spec.json', spec)
        write_new_json(run_root / 'matrix.json', spec['plan'])
        write_new_json(run_root / TIMING_HISTORY_NAME, _snapshot_cross_run_timing(paths, spec, current_run_id=chosen))
        atomic_write_json(run_root / 'run_state.json', _initial_state(chosen, spec))
    except Exception:
        shutil.rmtree(run_root)
        raise
    return (chosen, run_root)

def load_run(paths: Paths, run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    from .storage import read_json, resolve_inside
    run_root = resolve_inside(paths.runs, run_id, label='run_id')
    spec_path = run_root / 'run_spec.json'
    state_path = run_root / 'run_state.json'
    if not spec_path.is_file() or not state_path.is_file():
        raise BenchmarkError(f'run {run_id!r} does not contain run_spec.json and run_state.json')
    spec = read_json(spec_path)
    state = read_json(state_path)
    if int(spec.get('schema_version', -1)) != SCHEMA_VERSION:
        raise BenchmarkError(f"unsupported run spec schema: {spec.get('schema_version')!r}")
    if state.get('run_id') != run_id:
        raise BenchmarkError('run_state.json identifies a different run')
    return (run_root, spec, state)

def verify_run_inputs(paths: Paths, run_root: Path, spec: Mapping[str, Any], *, verify_automation: bool=True, verify_config: bool=True) -> None:
    """Validate that the run owns the executable and task snapshots it needs."""
    from .storage import read_json, resolve_inside
    execution = resolve_inside(
        run_root,
        spec.get('automation', {}).get('execution_snapshot', 'inputs/execution/benchmark_runtime'),
        label='execution snapshot',
    )
    required = ('__init__.py', 'contracts.py', 'execution.py', 'state.py')
    state = read_json(run_root / 'run_state.json')
    unfinished = any(
        cell.get('status') not in TERMINAL_CELL_STATES
        for cell in state.get('cells', {}).values()
    )
    if unfinished and (
        not execution.is_dir()
        or any(not (execution / name).is_file() for name in required)
    ):
        raise BenchmarkError(
            'unfinished run has no complete execution snapshot; choose an explicit restart or migration'
        )
    for case_id, case in spec['cases'].items():
        baseline = case['baseline']
        snapshot = resolve_inside(run_root, baseline['snapshot_workspace'], label=f'case {case_id} baseline snapshot')
        if not snapshot.is_dir():
            raise BenchmarkError(f'run-local baseline snapshot is missing for {case_id}')
        starting = case['starting_evidence']
        if starting['policy'] == 'snapshot':
            history = resolve_inside(run_root, starting['snapshot'], label=f'case {case_id} history snapshot')
            if not history.is_dir():
                raise BenchmarkError(f'run-local history snapshot is missing for {case_id}')
    for arm_id, arm in spec['arms'].items():
        templates = [arm['template']] if arm.get('template') else [
            item['path'] for item in arm.get('case_strategy_templates', {}).values()
        ]
        for template in templates:
            if not resolve_inside(run_root, template, label=f'arm {arm_id} strategy snapshot').is_file():
                raise BenchmarkError(f'run-local strategy snapshot is missing for {arm_id}')

def _save_state(run_root: Path, state: dict[str, Any], *, event: str | None=None, **details: Any) -> None:
    from .storage import atomic_write_json, utc_now
    now = utc_now()
    state['updated_utc'] = now
    if event:
        state.setdefault('events', []).append({'at': now, 'event': event, **details})
    atomic_write_json(run_root / 'run_state.json', state)

def _copy_declared_inputs(source: Path, destination: Path, include_paths: Sequence[str]) -> None:
    """Populate only declared task inputs into a freshly initialized workspace."""
    from .storage import resolve_inside
    if not destination.is_dir():
        raise BenchmarkError(f'fresh yadof workspace does not exist: {destination}')
    for raw in include_paths:
        src = resolve_inside(source, raw, label='baseline input')
        dst = resolve_inside(destination, raw, label='cell input')
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

def _apply_config_overrides(config_path: Path, overrides: Mapping[str, Any]) -> None:
    from .planning import config_overrides as _config_overrides
    current = config_path.read_text(encoding='utf-8')
    if CONFIG_BLOCK_START in current or CONFIG_BLOCK_END in current:
        raise BenchmarkError(f'managed config override block already exists in {config_path}')
    checked = _config_overrides(overrides, label='managed config overrides')
    lines = ['', CONFIG_BLOCK_START]
    for key in sorted(checked):
        lines.append(f'{key} = {checked[key]!r}')
    lines.extend([CONFIG_BLOCK_END, ''])
    with config_path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines))

def _copy_history_snapshot(snapshot: Path, workspace: Path) -> None:
    for source in sorted(snapshot.rglob('*'), key=lambda path: path.as_posix().casefold()):
        relative = source.relative_to(snapshot)
        destination = workspace / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

def _attempt_directory(run_root: Path, cell_id: str, attempt_number: int) -> Path:
    return run_root / 'cells' / cell_id / 'attempts' / f'{attempt_number:04d}'

def _prepare_attempt(config: Mapping[str, Any], paths: Paths, run_root: Path, spec: Mapping[str, Any], cell_plan: Mapping[str, Any], cell_state: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    from .planning import baseline_visualization_directory_name as _baseline_visualization_directory_name, visualization_file_prefix as _visualization_file_prefix
    from .storage import utc_now
    attempt_number = len(cell_state['attempts']) + 1
    attempt_root = _attempt_directory(run_root, cell_plan['cell_id'], attempt_number)
    attempt_root.mkdir(parents=True, exist_ok=False)
    workspace = attempt_root / 'workspace'
    baseline_directory = _baseline_visualization_directory_name(spec['cases'][cell_plan['case']]['baseline'])
    visualization_file_prefix = _visualization_file_prefix(str(cell_plan['cell_id']), attempt_number)
    attempt = {'attempt': attempt_number, 'replacement_for': attempt_number - 1 if attempt_number > 1 else None, 'status': 'prepared', 'created_utc': utc_now(), 'workspace': str(workspace), 'input_fingerprint': None, 'post_input_fingerprint': None, 'input_manifest': str(attempt_root / 'input_manifest.json'), 'visualization_output_dir': str(run_root / VISUALIZATION_DIRECTORY_NAME / baseline_directory), 'visualization_file_prefix': visualization_file_prefix, 'cost_visualization_output': str(run_root / VISUALIZATION_DIRECTORY_NAME / VIEW_COST_DIRECTORY_NAME / f'{visualization_file_prefix}{COST_PLOT_NAME}'), 'commands': [], 'sealed_utc': None, 'error': None}
    cell_state['attempts'].append(attempt)
    cell_state['status'] = 'running'
    return (attempt_root, attempt)

def _materialize_attempt_inputs(paths: Paths, run_root: Path, spec: Mapping[str, Any], cell_plan: Mapping[str, Any], attempt_root: Path, attempt: dict[str, Any]) -> None:
    from .storage import resolve_inside, task_fingerprint, task_manifest, write_new_json
    workspace = Path(attempt['workspace'])
    case_id = str(cell_plan['case'])
    case_spec = spec['cases'][case_id]
    baseline_workspace = resolve_inside(run_root, case_spec['baseline']['snapshot_workspace'], label=f'case {case_id} baseline snapshot')
    include_paths = case_spec['baseline']['include_paths']
    _copy_declared_inputs(baseline_workspace, workspace, include_paths)
    if case_spec['history_policy'] == 'snapshot':
        snapshot_value = case_spec['starting_evidence'].get('snapshot')
        if not snapshot_value:
            raise BenchmarkError(f'snapshot history policy has no frozen snapshot for {case_id}')
        snapshot = resolve_inside(run_root, snapshot_value, label=f'case {case_id} history snapshot')
        _copy_history_snapshot(snapshot, workspace)
    overrides: dict[str, Any] = {}
    if cell_plan['kind'] == 'measured':
        overrides.update(spec.get('runner', {}).get('measured_config_overrides', {}))
    overrides.update({'FAST_EVALUATION_MAX_WORKERS': int(case_spec['max_workers']), 'OPTIMIZE_SMOKE_TEST_ENABLED': False})
    if cell_plan['kind'] == 'measured':
        arm_id = str(cell_plan['arm'])
        arm_spec = spec['arms'][arm_id]
        selected_template = arm_spec.get('case_strategy_templates', {}).get(case_id)
        template_path = resolve_inside(
            run_root,
            arm_spec['template'] if selected_template is None else selected_template['path'],
            label=f'arm {arm_id} strategy snapshot',
        )
        overrides.update(arm_spec.get('config_overrides', {}))
        shutil.copy2(template_path, workspace / 'submit' / 'optimization.py')
    _apply_config_overrides(workspace / 'config.py', overrides)
    manifest = task_manifest(workspace, include_paths)
    fingerprint = task_fingerprint(workspace, include_paths)
    attempt['input_fingerprint'] = fingerprint
    write_new_json(attempt_root / 'input_manifest.json', {'schema_version': SCHEMA_VERSION, 'case': case_id, 'arm': cell_plan.get('arm'), 'seed': cell_plan['seed'], 'baseline_task_fingerprint': case_spec['baseline']['actual_task_fingerprint'], 'starting_evidence_fingerprint': case_spec['starting_evidence']['fingerprint'], 'fingerprint': fingerprint, 'files': manifest})


save_state = _save_state
prepare_attempt = _prepare_attempt
materialize_attempt_inputs = _materialize_attempt_inputs
