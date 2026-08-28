"""Planning services for benchmark automation."""
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

def load_config(config_path: Path, *, runs_dir_override: str | Path | None=None, invocation_cwd: Path | None=None) -> tuple[dict[str, Any], Paths]:
    from .storage import load_toml as _load_toml, resolve_inside, resolve_runs_dir
    config_path = config_path.resolve()
    root = config_path.parent
    config = _load_toml(config_path)
    if config.get('schema_version') != SCHEMA_VERSION:
        raise BenchmarkError(f"unsupported benchmark schema_version {config.get('schema_version')!r}; expected {SCHEMA_VERSION}")
    runner = config.get('runner')
    if not isinstance(runner, dict):
        raise BenchmarkError('missing [runner] table')
    paths = Paths(root=root, config=config_path, runs=resolve_runs_dir(root, str(runner.get('runs_dir', 'runs')), override=runs_dir_override, invocation_cwd=invocation_cwd), strategies=resolve_inside(root, str(runner.get('strategy_template_dir', 'strategy_templates')), label='strategy_template_dir'), histories=resolve_inside(root, str(runner.get('history_snapshot_dir', 'history_snapshots')), label='history_snapshot_dir'))
    validate_config(config, paths)
    return (config, paths)

def validate_config(config: Mapping[str, Any], paths: Paths) -> None:
    runner = config.get('runner', {})
    cases = config.get('cases')
    arms = config.get('arms')
    suites = config.get('suites')
    budgets = config.get('budgets')
    if not all((isinstance(item, dict) for item in (cases, arms, suites, budgets))):
        raise BenchmarkError('config requires [cases], [arms], [suites], and [budgets]')
    assert isinstance(runner, dict)
    assert isinstance(cases, dict) and isinstance(arms, dict)
    assert isinstance(suites, dict) and isinstance(budgets, dict)
    _config_overrides(runner.get('measured_config_overrides', {}), label='runner measured_config_overrides')
    _validate_paths_and_cases(runner, cases, paths)
    _validate_arms(arms, cases, paths)
    _validate_suites(suites, budgets, cases, arms)


def _validate_paths_and_cases(
    runner: Mapping[str, Any], cases: Mapping[str, Any], paths: Paths
) -> None:
    from .storage import baseline_identity, is_within, paths_overlap, read_json, resolve_inside
    if paths.runs.exists() and (not paths.runs.is_dir()):
        raise BenchmarkError(f'runs_dir is not a directory: {paths.runs}')
    if paths.runs == paths.root or is_within(paths.root, paths.runs):
        raise BenchmarkError('runs_dir must not be the benchmark root or contain it')
    for label, protected in (('strategy_template_dir', paths.strategies), ('history_snapshot_dir', paths.histories)):
        if paths_overlap(paths.runs, protected):
            raise BenchmarkError(f'runs_dir overlaps {label}: {protected}')
    for case_id, case in cases.items():
        if not isinstance(case, dict):
            raise BenchmarkError(f'case {case_id!r} must be a table')
        baseline = resolve_inside(paths.root, str(case.get('baseline', '')), label=f'case {case_id} baseline')
        if paths_overlap(paths.runs, baseline):
            raise BenchmarkError(f'runs_dir overlaps case {case_id!r} baseline: {baseline}')
        if not (baseline / 'baseline.json').is_file() or not (baseline / 'workspace').is_dir():
            raise BenchmarkError(f'case {case_id!r} baseline is incomplete: {baseline}')
        baseline_identity(paths, baseline, read_json(baseline / 'baseline.json'), case_id)
        include = case.get('include_paths')
        if not isinstance(include, list) or not include or (not all((isinstance(x, str) for x in include))):
            raise BenchmarkError(f'case {case_id!r} include_paths must be a non-empty string list')
        if POSTPROCESS_SCRIPT_NAME not in include:
            raise BenchmarkError(f'case {case_id!r} include_paths must declare {POSTPROCESS_SCRIPT_NAME!r}')
        if not (baseline / 'workspace' / POSTPROCESS_SCRIPT_NAME).is_file():
            raise BenchmarkError(f'case {case_id!r} baseline has no {POSTPROCESS_SCRIPT_NAME}: {baseline}')
        policy = case.get('history_policy')
        if policy not in {'empty', 'snapshot'}:
            raise BenchmarkError(f'case {case_id!r} history_policy must be empty or snapshot')
        if policy == 'snapshot':
            snapshot = resolve_inside(paths.histories, str(case.get('history_snapshot', '')), label='history snapshot')
            if not snapshot.is_dir():
                raise BenchmarkError(f'history snapshot does not exist: {snapshot}')


def _validate_arms(
    arms: Mapping[str, Any], cases: Mapping[str, Any], paths: Paths
) -> None:
    from .storage import resolve_inside
    for arm_id, arm in arms.items():
        if not isinstance(arm, dict):
            raise BenchmarkError(f'arm {arm_id!r} must be a table')
        display_name = arm.get('display_name', arm_id)
        if not isinstance(display_name, str) or not display_name.strip():
            raise BenchmarkError(f'arm {arm_id!r} display_name must be a non-empty string')
        case_templates = arm.get('case_strategy_templates')
        if case_templates is not None:
            if 'strategy_template' in arm:
                raise BenchmarkError(f'arm {arm_id!r} must choose strategy_template or case_strategy_templates, not both')
            if not isinstance(case_templates, dict) or not case_templates:
                raise BenchmarkError(f'arm {arm_id!r} case_strategy_templates must be a non-empty table')
            unknown_cases = sorted(set(case_templates) - set(cases))
            if unknown_cases:
                raise BenchmarkError(f'arm {arm_id!r} has templates for unknown cases: ' + ', '.join(unknown_cases))
            for case_id, template_name in case_templates.items():
                template = resolve_inside(paths.strategies, str(template_name), label=f'arm {arm_id} case {case_id} template')
                if not template.is_file():
                    raise BenchmarkError(f'strategy template does not exist: {template}')
        else:
            template = resolve_inside(paths.strategies, str(arm.get('strategy_template', '')), label=f'arm {arm_id} template')
            if not template.is_file():
                raise BenchmarkError(f'strategy template does not exist: {template}')
        _config_overrides(arm.get('config_overrides', {}), label=f'arm {arm_id} config_overrides')


def _validate_suites(
    suites: Mapping[str, Any],
    budgets: Mapping[str, Any],
    cases: Mapping[str, Any],
    arms: Mapping[str, Any],
) -> None:
    for suite_id, suite in suites.items():
        if not isinstance(suite, dict):
            raise BenchmarkError(f'suite {suite_id!r} must be a table')
        purpose = suite.get('purpose')
        if purpose not in {'structural', 'performance'}:
            raise BenchmarkError(f'suite {suite_id!r} purpose must be structural or performance')
        suite_cases = suite.get('cases', [])
        suite_arms = suite.get('arms', [])
        seeds = suite.get('seeds', [])
        if not suite_cases or not all((case in cases for case in suite_cases)):
            raise BenchmarkError(f'suite {suite_id!r} names an unknown or empty case set')
        if not all((arm in arms for arm in suite_arms)):
            raise BenchmarkError(f'suite {suite_id!r} names an unknown arm')
        for arm_id in suite_arms:
            case_templates = arms[arm_id].get('case_strategy_templates')
            if isinstance(case_templates, dict):
                missing = sorted(set(suite_cases) - set(case_templates))
                if missing:
                    raise BenchmarkError(f'suite {suite_id!r} arm {arm_id!r} has no case strategy template for: ' + ', '.join(missing))
        if not seeds or not all((isinstance(seed, int) and seed >= 0 for seed in seeds)):
            raise BenchmarkError(f'suite {suite_id!r} seeds must be non-negative integers')
        smoke_only = bool(suite.get('smoke_only', False))
        if smoke_only and suite_arms:
            raise BenchmarkError(f'suite {suite_id!r} smoke_only suite must have no arms')
        if not smoke_only:
            suite_budget = budgets.get(suite_id)
            if not isinstance(suite_budget, dict):
                raise BenchmarkError(f'suite {suite_id!r} has no budget table')
            _validate_suite_budgets(
                suite_id, purpose, suite_cases, suite_arms, suite_budget
            )


def _validate_suite_budgets(
    suite_id: str,
    purpose: str,
    suite_cases: Sequence[str],
    suite_arms: Sequence[str],
    suite_budget: Mapping[str, Any],
) -> None:
    for case_id in suite_cases:
        case_budget = suite_budget.get(case_id)
        if not isinstance(case_budget, dict):
            raise BenchmarkError(f'suite {suite_id!r} case {case_id!r} has no budget')
        attempted_by_arm: list[int] = []
        for arm_id in suite_arms:
            budget = case_budget.get(arm_id)
            if not isinstance(budget, dict):
                raise BenchmarkError(f'suite {suite_id!r} case {case_id!r} arm {arm_id!r} has no budget')
            pop = budget.get('population')
            generations = budget.get('generations')
            maximum = budget.get('max_generations', generations)
            if not all((isinstance(x, int) and x > 0 for x in (pop, generations, maximum))):
                raise BenchmarkError(f'invalid positive integer budget for {suite_id}/{case_id}/{arm_id}')
            if maximum < generations:
                raise BenchmarkError(f'max_generations is below generations for {suite_id}/{case_id}/{arm_id}')
            attempted_by_arm.append(int(pop) * int(generations))
        if purpose == 'performance' and len(set(attempted_by_arm)) > 1:
            raise BenchmarkError(f'performance suite {suite_id!r} case {case_id!r} has unequal planned attempted budgets')

def _safe_id(value: str) -> str:
    cleaned = re.sub('[^a-zA-Z0-9._-]+', '-', value.strip()).strip('-._')
    return cleaned or 'run'

def _config_overrides(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BenchmarkError(f'{label} must be a table')
    overrides = dict(value)
    for key in overrides:
        if not isinstance(key, str) or not re.fullmatch('[A-Z][A-Z0-9_]*', key):
            raise BenchmarkError(f'unsafe config override name in {label}: {key!r}')
    return overrides

def _cell_id(case_id: str, arm_id: str | None, seed: int, *, kind: str) -> str:
    if kind == 'smoke':
        return _safe_id(f'smoke__{case_id}__seed-{seed}')
    return _safe_id(f'{case_id}__{arm_id}__seed-{seed}')

def _select_values(allowed: Sequence[Any], requested: Sequence[Any] | None, *, label: str) -> list[Any]:
    if requested is None:
        return list(allowed)
    unknown = [value for value in requested if value not in allowed]
    if unknown:
        raise BenchmarkError(f'unknown {label} selection(s) {unknown!r}; allowed: {list(allowed)!r}')
    requested_set = set(requested)
    selected = [value for value in allowed if value in requested_set]
    if not selected:
        raise BenchmarkError(f'{label} selection is empty')
    return selected

def _cost_view_command(python: str, workspace: str | Path, output_path: str | Path) -> list[str]:
    return [python, '-m', 'yadof', 'view', 'cost', '--workspace', str(workspace), '--output', str(output_path)]

def _postprocess_command(python: str, workspace: str | Path, output_dir: str | Path, output_prefix: str) -> list[str]:
    workspace_path = Path(workspace)
    return [python, str(workspace_path / POSTPROCESS_SCRIPT_NAME), '--workspace', str(workspace_path), '--output-dir', str(output_dir), '--output-prefix', output_prefix]

def _visualization_file_prefix(cell_id: str, attempt_number: int) -> str:
    return f'{cell_id}__attempt-{attempt_number:04d}__'

def _baseline_visualization_directory_name(baseline: str | Path | Mapping[str, Any]) -> str:
    if isinstance(baseline, Mapping):
        value = baseline.get('baseline_id')
    else:
        value = Path(baseline).name
    if not isinstance(value, str) or not value or _safe_id(value) != value:
        raise BenchmarkError(f'invalid baseline visualization directory name: {value!r}')
    return value

def _planned_commands(config: Mapping[str, Any], cell: Mapping[str, Any]) -> list[list[str]]:
    python = str(Path(sys.executable).resolve())
    workspace = f"<run-root>/cells/{cell['cell_id']}/attempts/<attempt>/workspace"
    case = config['cases'][cell['case']]
    baseline_directory = _baseline_visualization_directory_name(case['baseline'])
    visualization_prefix = f"{cell['cell_id']}__attempt-<attempt>__"
    commands = [[python, '-m', 'yadof', 'init', workspace]]
    commands.append([python, '-m', 'yadof', 'check', '--workspace', workspace])
    if cell['kind'] == 'smoke':
        commands.append([python, '-m', 'yadof', 'smoke-test', '--workspace', workspace, '--mode', str(case['mode']), '--real-task'])
        return commands
    commands.append([python, '-m', 'yadof', 'run', '--workspace', workspace, '--generations', str(cell['generations']), '--start-generation', '0', '--mode', str(case['mode']), '--population-size', str(cell['population']), '--random-seed', str(cell['seed']), '--no-smoke-test', '--progress', '--fail-on-all-infinite'])
    if int(cell['max_generations']) > int(cell['generations']):
        commands.append([python, '-m', 'yadof', 'run', '--workspace', workspace, '--generations', str(int(cell['max_generations']) - int(cell['generations'])), '--start-generation', str(cell['generations']), '--mode', str(case['mode']), '--population-size', str(cell['population']), '--random-seed', str(cell['seed']), '--no-smoke-test', '--progress', '--fail-on-all-infinite'])
    commands.append(_postprocess_command(python, workspace, f'<run-root>/{VISUALIZATION_DIRECTORY_NAME}/{baseline_directory}', visualization_prefix))
    commands.append(_cost_view_command(python, workspace, f"<run-root>/{VISUALIZATION_DIRECTORY_NAME}/{VIEW_COST_DIRECTORY_NAME}/{cell['cell_id']}__attempt-<attempt>__{COST_PLOT_NAME}"))
    return commands

def build_plan(config: Mapping[str, Any], paths: Paths, suite_id: str, *, case_ids: Sequence[str] | None=None, arm_ids: Sequence[str] | None=None, seeds: Sequence[int] | None=None) -> dict[str, Any]:
    suites = config['suites']
    if suite_id not in suites:
        raise BenchmarkError(f"unknown suite {suite_id!r}; choose from {', '.join(sorted(suites))}")
    suite = suites[suite_id]
    selected_cases = _select_values(suite['cases'], case_ids, label='case')
    selected_arms = _select_values(suite.get('arms', []), arm_ids, label='arm') if suite.get('arms') else []
    if arm_ids and (not suite.get('arms')):
        raise BenchmarkError(f'suite {suite_id!r} has no measured arms to filter')
    selected_seeds = [int(seed) for seed in _select_values(suite['seeds'], seeds, label='seed')]
    cells: list[dict[str, Any]] = []
    if bool(suite.get('smoke', False)):
        for case_id in selected_cases:
            seed = selected_seeds[0]
            cells.append({'cell_id': _cell_id(case_id, None, seed, kind='smoke'), 'kind': 'smoke', 'case': case_id, 'arm': None, 'seed': seed, 'population': 1, 'generations': 0, 'max_generations': 0, 'planned_attempted_evaluations': 1, 'disposable': True})
    if not bool(suite.get('smoke_only', False)):
        budgets = config['budgets'][suite_id]
        for case_id in selected_cases:
            for seed in selected_seeds:
                for arm_id in selected_arms:
                    budget = budgets[case_id][arm_id]
                    population = int(budget['population'])
                    generations = int(budget['generations'])
                    cells.append({'cell_id': _cell_id(case_id, arm_id, seed, kind='measured'), 'kind': 'measured', 'case': case_id, 'arm': arm_id, 'seed': seed, 'population': population, 'generations': generations, 'max_generations': int(budget.get('max_generations', generations)), 'planned_attempted_evaluations': population * generations, 'disposable': False})
    for cell in cells:
        cell['planned_commands'] = _planned_commands(config, cell)
    estimated_eval_sec = 0.0
    estimated_storage_mib = 0.0
    for cell in cells:
        case = config['cases'][cell['case']]
        workers = max(1, int(case.get('max_workers', 1)))
        estimated_eval_sec += float(case.get('observed_eval_sec', 0.0)) * int(cell['planned_attempted_evaluations']) / workers
        estimated_storage_mib += float(case.get('estimated_record_mib', 0.0)) * int(cell['planned_attempted_evaluations'])
    return {'schema_version': SCHEMA_VERSION, 'suite': suite_id, 'purpose': suite['purpose'], 'fail_fast': bool(suite.get('fail_fast', suite['purpose'] == 'structural')), 'smoke_is_disposable': True, 'selection': {'cases': selected_cases, 'arms': selected_arms, 'seeds': selected_seeds}, 'cell_count': len(cells), 'cells': cells, 'estimates': {'evaluation_wall_lower_bound_sec': estimated_eval_sec, 'record_storage_mib': estimated_storage_mib, 'scope_note': 'Task evaluation estimate excludes optimizer and surrogate training overhead.'}, 'prerequisites': {case_id: dict(config['cases'][case_id].get('resource', {})) for case_id in selected_cases}}

def _package_identity() -> dict[str, Any]:
    from .storage import file_sha256
    import yadof
    origin = Path(yadof.__file__).resolve()
    identity: dict[str, Any] = {'version': str(getattr(yadof, '__version__', 'unknown')), 'origin': str(origin), 'module_sha256': file_sha256(origin), 'python': str(Path(sys.executable).resolve()), 'python_version': sys.version}
    with contextlib.suppress(importlib.metadata.PackageNotFoundError, OSError):
        distribution = importlib.metadata.distribution('yadof')
        identity['distribution_name'] = distribution.metadata.get('Name', 'yadof')
        identity['distribution_version'] = distribution.version
        record = next((Path(distribution.locate_file(file)).resolve() for file in distribution.files or () if str(file).replace('\\', '/').endswith('.dist-info/RECORD')), None)
        if record is not None and record.is_file():
            identity['distribution_record'] = str(record)
            identity['distribution_record_sha256'] = file_sha256(record)
    return identity

def _baseline_details(config: Mapping[str, Any], paths: Paths, case_id: str) -> dict[str, Any]:
    from .storage import baseline_identity as _baseline_identity, read_json, resolve_inside, task_fingerprint, task_manifest
    case = config['cases'][case_id]
    root = resolve_inside(paths.root, case['baseline'], label=f'case {case_id} baseline')
    manifest = read_json(root / 'baseline.json')
    workspace = root / 'workspace'
    actual = task_fingerprint(workspace, case['include_paths'])
    runtime_paths = [relative for relative in RUNTIME_PATHS if (workspace / relative).exists()]
    identity = _baseline_identity(paths, root, manifest, case_id)
    return {'root': str(root), 'workspace': str(workspace), 'baseline_id': manifest.get('baseline_id'), 'yadof_version': manifest.get('yadof_version'), 'expected_task_fingerprint': manifest.get('task_fingerprint'), 'actual_task_fingerprint': actual, 'task_file_count': len(task_manifest(workspace, case['include_paths'])), 'fingerprint_matches': actual == manifest.get('task_fingerprint'), 'runtime_paths_present': runtime_paths, 'runtime_clean': not runtime_paths, 'include_paths': list(case['include_paths']), **identity}

def _strategy_details(config: Mapping[str, Any], paths: Paths, arm_id: str) -> dict[str, Any]:
    from .storage import file_sha256, resolve_inside
    arm = config['arms'][arm_id]
    configured = arm.get('case_strategy_templates')
    template_names = {str(case_id): str(value) for case_id, value in configured.items()} if isinstance(configured, dict) else {'*': str(arm['strategy_template'])}
    template_details: dict[str, dict[str, str]] = {}
    constructed_types: set[str] = set()
    for case_id, template_name in sorted(template_names.items()):
        template = resolve_inside(paths.strategies, template_name, label=f'arm {arm_id} case {case_id} template')
        module_name = f"benchmark_strategy_{_safe_id(arm_id).replace('-', '_')}_{_safe_id(case_id).replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, template)
        if spec is None or spec.loader is None:
            raise BenchmarkError(f'cannot load strategy template: {template}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        builder = getattr(module, 'build_optimization', None)
        if not callable(builder):
            raise BenchmarkError(f'strategy {template} has no callable build_optimization')
        strategy = builder()
        constructed_types.add(f'{type(strategy).__module__}.{type(strategy).__qualname__}')
        template_details[case_id] = {'path': str(template), 'sha256': file_sha256(template)}
    if len(constructed_types) != 1:
        raise BenchmarkError(f'arm {arm_id!r} case strategies construct different component types')
    default = template_details.get('*')
    return {'template': None if default is None else default['path'], 'sha256': None if default is None else default['sha256'], 'case_strategy_templates': {} if default is not None else template_details, 'constructed_type': next(iter(constructed_types)), 'display_name': str(arm.get('display_name', arm_id)), 'surrogate': bool(arm.get('surrogate', False)), 'config_overrides': _config_overrides(arm.get('config_overrides', {}), label=f'arm {arm_id} config_overrides')}

def _run_read_only(command: Sequence[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, check=False)
        return {'command': list(command), 'returncode': result.returncode, 'duration_sec': time.perf_counter() - started, 'stdout': result.stdout, 'stderr': result.stderr}
    except subprocess.TimeoutExpired as exc:
        return {'command': list(command), 'returncode': None, 'duration_sec': time.perf_counter() - started, 'stdout': exc.stdout or '' if isinstance(exc.stdout, str) else '', 'stderr': exc.stderr or '' if isinstance(exc.stderr, str) else '', 'error': f'timed out after {timeout} seconds'}

def preflight(config: Mapping[str, Any], paths: Paths, suite_id: str, *, case_ids: Sequence[str] | None=None, arm_ids: Sequence[str] | None=None, seeds: Sequence[int] | None=None) -> dict[str, Any]:
    from .storage import existing_disk_root as _existing_disk_root, utc_now
    plan = build_plan(config, paths, suite_id, case_ids=case_ids, arm_ids=arm_ids, seeds=seeds)
    identity = _package_identity()
    checks: list[dict[str, Any]] = []
    baseline_map: dict[str, Any] = {}
    strategy_map: dict[str, Any] = {}
    resource_map: dict[str, Any] = {}
    for case_id in plan['selection']['cases']:
        try:
            details = _baseline_details(config, paths, case_id)
            baseline_map[case_id] = details
            creation_version = details['yadof_version']
            provenance_version_ok = bool(isinstance(creation_version, str) and creation_version.strip())
            details['execution_yadof_version'] = identity['version']
            details['creation_version_matches_execution'] = creation_version == identity['version']
            baseline_ok = bool(details['runtime_clean'] and provenance_version_ok)
            checks.append({'name': f'baseline:{case_id}', 'ok': baseline_ok, 'details': details, 'error': None if baseline_ok else 'baseline provenance version is missing or mutable runtime paths are present'})
            result = _run_read_only([identity['python'], '-m', 'yadof', 'check', '--workspace', details['workspace']], cwd=paths.root, timeout=300)
            checks.append({'name': f'yadof-check:{case_id}', 'ok': result['returncode'] == 0, 'details': result})
        except Exception as exc:
            checks.append({'name': f'baseline:{case_id}', 'ok': False, 'error': str(exc)})
        resource = config['cases'][case_id].get('resource', {})
        kind = resource.get('kind')
        if kind == 'environment_executable':
            variable = str(resource.get('variable', ''))
            value = os.environ.get(variable)
            exists = bool(value and Path(value).is_file())
            checks.append({'name': f'resource:{case_id}', 'ok': exists, 'details': {'kind': kind, 'variable': variable, 'value': value, 'exists': exists}})
            resource_map[case_id] = checks[-1]['details']
        elif kind == 'cuda':
            try:
                import torch
                available = bool(torch.cuda.is_available())
                details = {'kind': 'cuda', 'torch_version': str(torch.__version__), 'available': available, 'device': torch.cuda.get_device_name(0) if available else None}
                checks.append({'name': f'resource:{case_id}', 'ok': available, 'details': details})
                resource_map[case_id] = details
            except Exception as exc:
                checks.append({'name': f'resource:{case_id}', 'ok': False, 'error': str(exc)})
    for arm_id in plan['selection']['arms']:
        try:
            strategy_map[arm_id] = _strategy_details(config, paths, arm_id)
            checks.append({'name': f'strategy:{arm_id}', 'ok': True, 'details': strategy_map[arm_id]})
        except Exception as exc:
            checks.append({'name': f'strategy:{arm_id}', 'ok': False, 'error': str(exc)})
    runner = config['runner']
    disk_root = _existing_disk_root(paths.runs)
    free_mib = shutil.disk_usage(disk_root).free / (1024 * 1024)
    required_mib = max(float(runner.get('minimum_free_disk_mib', 0)), float(plan['estimates']['record_storage_mib']) * 2.0)
    checks.append({'name': 'disk-space', 'ok': free_mib >= required_mib, 'details': {'free_mib': free_mib, 'required_mib': required_mib, 'path': str(disk_root)}})
    installed_distribution_ok = bool(identity.get('distribution_record_sha256')) and identity.get('distribution_version') == identity.get('version')
    checks.append({'name': 'python-environment', 'ok': installed_distribution_ok, 'details': identity, 'error': None if installed_distribution_ok else 'yadof must be an installed distribution with matching metadata and RECORD'})
    return {'schema_version': SCHEMA_VERSION, 'suite': suite_id, 'ok': all((bool(check.get('ok')) for check in checks)), 'checked_utc': utc_now(), 'host': {'node': platform.node(), 'platform': platform.platform()}, 'package': identity, 'plan': plan, 'baselines': baseline_map, 'strategies': strategy_map, 'resources': resource_map, 'checks': checks}

def build_run_spec(config: Mapping[str, Any], paths: Paths, suite_id: str, preflight_result: Mapping[str, Any], *, label: str | None=None) -> dict[str, Any]:
    from .storage import directory_fingerprint, directory_manifest, file_sha256, object_sha256, resolve_inside, utc_now
    if not preflight_result.get('ok'):
        raise BenchmarkError('preflight failed; no run directory was created')
    plan = dict(preflight_result['plan'])
    suite = config['suites'][suite_id]
    cases: dict[str, Any] = {}
    for case_id in plan['selection']['cases']:
        case = config['cases'][case_id]
        baseline = dict(preflight_result['baselines'][case_id])
        baseline['source_workspace'] = baseline.pop('workspace')
        baseline['snapshot_workspace'] = (Path('inputs') / 'baselines' / case_id / 'workspace').as_posix()
        if case['history_policy'] == 'empty':
            starting_evidence = {'policy': 'empty', 'snapshot': None, 'fingerprint': object_sha256({'policy': 'empty', 'rows': 0, 'checkpoints': 0}), 'file_count': 0}
        else:
            snapshot = resolve_inside(paths.histories, case['history_snapshot'], label=f'case {case_id} history snapshot')
            manifest = directory_manifest(snapshot)
            starting_evidence = {
                'policy': 'snapshot',
                'source_snapshot': str(snapshot),
                'snapshot': (Path('inputs') / 'histories' / case_id).as_posix(),
                'fingerprint': directory_fingerprint(snapshot),
                'file_count': len(manifest),
                'manifest': manifest,
            }
        cases[case_id] = {'baseline': baseline, 'mode': case['mode'], 'history_policy': case['history_policy'], 'history_snapshot': case.get('history_snapshot'), 'starting_evidence': starting_evidence, 'expected_objectives': int(case['expected_objectives']), 'rawdata_shapes': dict(case.get('rawdata_shapes', {})), 'max_workers': int(case.get('max_workers', 1)), 'observed_eval_sec': float(case.get('observed_eval_sec', 0.0)), 'representative_expensive_generation_sec': case.get('representative_expensive_generation_sec'), 'resource': dict(case.get('resource', {})), 'resolved_resource': dict(preflight_result.get('resources', {}).get(case_id, {}))}
    arms: dict[str, Any] = {}
    for arm_id in plan['selection']['arms']:
        arm = dict(preflight_result['strategies'][arm_id])
        if arm.get('template'):
            arm['source_template'] = arm['template']
            arm['template'] = (Path('inputs') / 'strategies' / arm_id / 'optimization.py').as_posix()
        else:
            templates = {}
            for case_id, item in arm.get('case_strategy_templates', {}).items():
                frozen = dict(item)
                frozen['source_path'] = frozen['path']
                frozen['path'] = (Path('inputs') / 'strategies' / arm_id / case_id / 'optimization.py').as_posix()
                templates[case_id] = frozen
            arm['case_strategy_templates'] = templates
        arms[arm_id] = arm
    automation_root = Path(__file__).resolve().parents[1]
    runtime_root = Path(__file__).resolve().parent
    payload: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'created_utc': utc_now(),
        'suite': suite_id,
        'purpose': suite['purpose'],
        'label': label,
        'config': {'path': str(paths.config), 'sha256': file_sha256(paths.config)},
        'package': dict(preflight_result['package']),
        'host': dict(preflight_result['host']),
        'automation': {
            'execution_snapshot': (Path('inputs') / 'execution' / 'benchmark_runtime').as_posix(),
            'sources': {
                'facade': {'path': str(automation_root / 'benchmark_core.py'), 'sha256': file_sha256(automation_root / 'benchmark_core.py')},
                'entrypoint': {'path': str(automation_root / 'benchmark.py'), 'sha256': file_sha256(automation_root / 'benchmark.py')},
                'runtime': {'path': str(runtime_root), 'sha256': directory_fingerprint(runtime_root)},
            },
        },
        'runner': {
            'command_timeout_sec': int(config['runner'].get('command_timeout_sec', 7200)),
            'audit_sample_percent': int(config['runner'].get('audit_sample_percent', 10)),
            'audit_random_seed': int(config['runner'].get('audit_random_seed', 0)),
            'fail_fast': bool(plan['fail_fast']),
            'measured_config_overrides': _config_overrides(config['runner'].get('measured_config_overrides', {}), label='runner measured_config_overrides'),
        },
        'cases': cases,
        'arms': arms,
        'plan': plan,
    }
    payload['spec_sha256'] = object_sha256(payload)
    return payload

def make_run_id(spec: Mapping[str, Any], label: str | None=None) -> str:
    stamp = dt.datetime.now(dt.UTC).strftime('%Y%m%d_%H%M%S')
    suffix = str(spec['spec_sha256'])[:12]
    middle = f'-{_safe_id(label)}' if label else ''
    return f'{stamp}{middle}-{suffix}'

def summarize_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded planning view that omits expanded command lines."""
    from .storage import json_safe as _json_safe
    by_case: dict[str, dict[str, int]] = {}
    smoke_count = 0
    measured_count = 0
    attempted_total = 0
    for cell in plan.get('cells', []):
        case_id = str(cell.get('case'))
        bucket = by_case.setdefault(case_id, {'cells': 0, 'smoke_cells': 0, 'measured_cells': 0, 'planned_attempted_evaluations': 0})
        attempted = int(cell.get('planned_attempted_evaluations', 0))
        kind = str(cell.get('kind'))
        bucket['cells'] += 1
        bucket['planned_attempted_evaluations'] += attempted
        attempted_total += attempted
        if kind == 'smoke':
            smoke_count += 1
            bucket['smoke_cells'] += 1
        else:
            measured_count += 1
            bucket['measured_cells'] += 1
    return _json_safe({'schema_version': plan.get('schema_version', SCHEMA_VERSION), 'view': 'plan-summary', 'suite': plan.get('suite'), 'purpose': plan.get('purpose'), 'selection': plan.get('selection', {}), 'fail_fast': plan.get('fail_fast'), 'cells': {'total': int(plan.get('cell_count', smoke_count + measured_count)), 'smoke': smoke_count, 'measured': measured_count, 'planned_attempted_evaluations': attempted_total, 'by_case': by_case}, 'estimates': plan.get('estimates', {}), 'prerequisites': plan.get('prerequisites', {}), 'detail': {'available_with': 'plan --full-json', 'omitted': ['expanded cell objects', 'planned command lines']}})

def _tail_text(value: Any, limit: int=600) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f'...{text[-limit:]}'

def summarize_preflight(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return check outcomes without embedding commands, stdout, or stderr."""
    from .storage import json_safe as _json_safe
    checks: list[dict[str, Any]] = []
    for check in result.get('checks', []):
        compact: dict[str, Any] = {'name': check.get('name'), 'ok': bool(check.get('ok'))}
        if check.get('error'):
            compact['error'] = check.get('error')
        details = check.get('details')
        if isinstance(details, Mapping):
            selected = {key: details.get(key) for key in ('kind', 'variable', 'exists', 'available', 'device', 'returncode', 'timed_out', 'free_mib', 'required_mib') if key in details}
            if selected:
                compact['details'] = selected
            if not compact['ok']:
                diagnostic = _tail_text(details.get('stderr')) or _tail_text(details.get('stdout'))
                if diagnostic:
                    compact['diagnostic_tail'] = diagnostic
        checks.append(compact)
    package = result.get('package', {})
    plan = summarize_plan(result.get('plan', {}))
    plan.pop('detail', None)
    passed = sum((1 for check in checks if check['ok']))
    return _json_safe({'schema_version': result.get('schema_version', SCHEMA_VERSION), 'view': 'preflight-summary', 'suite': result.get('suite'), 'ok': bool(result.get('ok')), 'checked_utc': result.get('checked_utc'), 'checks': {'total': len(checks), 'passed': passed, 'failed': len(checks) - passed, 'items': checks}, 'package': {'version': package.get('version'), 'origin': package.get('origin'), 'python': package.get('python'), 'python_version': str(package.get('python_version', '')).splitlines()[0]}, 'plan': plan, 'detail': {'available_with': 'preflight --full-json', 'omitted': ['command stdout/stderr', 'full package fingerprints', 'expanded plan cells']}})


safe_id = _safe_id
config_overrides = _config_overrides
cost_view_command = _cost_view_command
postprocess_command = _postprocess_command
visualization_file_prefix = _visualization_file_prefix
baseline_visualization_directory_name = _baseline_visualization_directory_name
run_read_only = _run_read_only
