"""Results services for benchmark automation."""
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


def _collector_identity() -> dict[str, str]:
    from .storage import file_sha256

    automation_root = Path(__file__).resolve().parents[1]
    core_path = automation_root / 'benchmark_core.py'
    entrypoint_path = automation_root / 'benchmark.py'
    return {
        'core_path': str(core_path),
        'core_sha256': file_sha256(core_path),
        'entrypoint_sha256': file_sha256(entrypoint_path),
    }

def _capture_json_cli(command: Sequence[str], *, cwd: Path, evidence_dir: Path, stem: str, timeout: int) -> dict[str, Any]:
    from .planning import run_read_only as _run_read_only
    from .storage import json_safe as _json_safe, write_new_text as _write_new_text, file_sha256, write_new_json
    result = _run_read_only(command, cwd=cwd, timeout=timeout)
    stdout_path = evidence_dir / f'{stem}.stdout.log'
    stderr_path = evidence_dir / f'{stem}.stderr.log'
    _write_new_text(stdout_path, str(result.get('stdout', '')))
    _write_new_text(stderr_path, str(result.get('stderr', '')))
    parsed: Any = None
    parse_error: str | None = None
    if result.get('returncode') == 0:
        try:
            parsed = json.loads(str(result.get('stdout', '')))
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    metadata = {'command': list(command), 'cwd': str(cwd), 'returncode': result.get('returncode'), 'duration_sec': result.get('duration_sec'), 'error': result.get('error'), 'parse_error': parse_error, 'stdout': str(stdout_path), 'stderr': str(stderr_path), 'stdout_sha256': file_sha256(stdout_path), 'stderr_sha256': file_sha256(stderr_path)}
    write_new_json(evidence_dir / f'{stem}.command.json', _json_safe(metadata))
    if parsed is not None:
        write_new_json(evidence_dir / f'{stem}.json', _json_safe(parsed))
    return {'metadata': metadata, 'payload': parsed}

def _generation_metadata(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    generations = [item for item in items if item.get('record_type') == 'generation' or ('generation_index' in item and ('population_size' in item or 'created_job_names' in item))]
    return sorted(generations, key=lambda item: (str(item.get('run_id', '')), int(item.get('optimization_index', 0) or 0), int(item.get('generation_index', 0) or 0)))

def _attempted_count(generations: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in generations:
        population_size = item.get('population_size')
        if isinstance(population_size, int):
            total += population_size
        else:
            names = item.get('created_job_names')
            if isinstance(names, list):
                total += len(names)
    return total

def _initial_population_fingerprint(generations: Sequence[Mapping[str, Any]], normalized_variables: Mapping[str, Sequence[float]], records: Sequence[Mapping[str, Any]]) -> tuple[str | None, int, str | None]:
    from .storage import object_sha256
    generation_zero = [item for item in generations if int(item.get('generation_index', -1)) == 0]
    if not generation_zero:
        return (None, 0, 'public optimization metadata has no generation 0')
    names = generation_zero[0].get('created_job_names')
    if not isinstance(names, list) or not names:
        return (None, 0, 'generation 0 metadata has no created_job_names')
    generation_names = {str(name) for name in names}
    indexed_names = [(int(record['population_index']), str(record['job_name'])) for record in records if str(record.get('job_name')) in generation_names and isinstance(record.get('population_index'), int)]
    if len(indexed_names) != len(generation_names):
        return (None, 0, 'population_index is unavailable for one or more generation-0 jobs')
    indexed_names.sort(key=lambda item: item[0])
    indices = [index for index, _name in indexed_names]
    if indices != list(range(len(indexed_names))):
        return (None, 0, f'generation-0 population_index sequence is not contiguous: {indices}')
    ordered_names = [name for _index, name in indexed_names]
    missing = [name for name in ordered_names if name not in normalized_variables]
    if missing:
        return (None, 0, f'normalized variables unavailable for {len(missing)} generation-0 jobs')
    matrix = [[float(value) for value in normalized_variables[str(name)]] for name in ordered_names]
    return (object_sha256(matrix), len(matrix), None)

def _rawdata_shapes(workspace: Path, records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[int]], str | None]:
    from yadof.job_template.rawdata_contract import load_rawdata_views
    from yadof.recorded_data import get_rawdata_samples
    completed = [item for item in records if item.get('status') == 'completed']
    if not completed:
        return ({}, 'no completed record is available for rawData shape inspection')
    job_name = str(completed[-1]['job_name'])
    samples = get_rawdata_samples(workspace, job_names=[job_name], status='completed')
    if not samples:
        return ({}, f'public rawData API returned no sample for {job_name}')
    _name, items = samples[-1]
    return ({view.name: [int(x) for x in view.data.shape] for view in load_rawdata_views(items)}, None)

def _command_validity(attempt: Mapping[str, Any]) -> dict[str, Any]:
    from .storage import read_json
    commands: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path_value in attempt.get('commands', []):
        try:
            metadata = read_json(Path(path_value))
        except BenchmarkError:
            continue
        stdout_path = Path(str(metadata.get('stdout', '')))
        stdout = ''
        if stdout_path.is_file():
            with contextlib.suppress(OSError):
                stdout = stdout_path.read_text(encoding='utf-8', errors='replace')
        if metadata.get('label') == 'check':
            warnings.extend((line.strip() for line in stdout.splitlines() if line.lstrip().startswith('[WARN]')))
        commands.append({'label': metadata.get('label'), 'returncode': metadata.get('returncode'), 'timed_out': metadata.get('timed_out'), 'duration_sec': metadata.get('duration_sec'), 'metadata': str(path_value)})
    return {'commands': commands, 'yadof_check_warnings': warnings}

def _finite_cost_row(row: Mapping[str, Any]) -> bool:
    costs = row.get('costs')
    return isinstance(costs, (list, tuple)) and bool(costs) and all((isinstance(value, (int, float)) and math.isfinite(float(value)) for value in costs))

def _load_cell_public_data(
    cell_plan: Mapping[str, Any], cell_state: Mapping[str, Any]
) -> tuple[dict[str, Any], tuple[Any, ...] | None]:
    from yadof import recorded_data
    from yadof.tools import cost_viewer
    result: dict[str, Any] = {'cell_id': cell_plan['cell_id'], 'kind': cell_plan['kind'], 'case': cell_plan['case'], 'arm': cell_plan['arm'], 'seed': cell_plan['seed'], 'execution_status': cell_state['status'], 'eligible_for_primary_performance_aggregate': False, 'exclusion_reason': None, 'attempt': None, 'validity': None, 'metrics': None, 'public_api_issues': []}
    attempts = list(cell_state.get('attempts', []))
    if not attempts:
        result['exclusion_reason'] = 'cell has no attempt workspace'
        return result, None
    attempt = attempts[-1]
    result['attempt'] = {'number': attempt.get('attempt'), 'replacement_for': attempt.get('replacement_for'), 'status': attempt.get('status'), 'workspace': attempt.get('workspace'), 'input_fingerprint': attempt.get('input_fingerprint'), 'post_input_fingerprint': attempt.get('post_input_fingerprint'), 'input_unchanged': attempt.get('input_fingerprint') == attempt.get('post_input_fingerprint'), 'error': attempt.get('error')}
    workspace = Path(str(attempt['workspace']))
    if not workspace.is_dir():
        result['exclusion_reason'] = 'latest attempt workspace does not exist'
        return result, None
    issues: list[str] = []
    objective_names_out: list[str] = []
    try:
        rows = cost_viewer.build_rows(workspace, status='completed', issues=issues, objective_names_out=objective_names_out)
        objectives = objective_names_out or cost_viewer.objective_names(workspace, rows)
        cost_view_summary = cost_viewer.summarize_rows(workspace, rows, resolved_objective_names=objectives, issues=issues)
    except Exception as exc:
        rows = []
        objectives = []
        cost_view_summary = None
        issues.append(f'cost_viewer collection failed: {exc}')
    try:
        records = list(recorded_data.list_records(workspace))
    except Exception as exc:
        records = []
        issues.append(f'list_records failed: {exc}')
    try:
        optimization_metadata = list(recorded_data.list_optimization_metadata(workspace))
    except Exception as exc:
        optimization_metadata = []
        issues.append(f'list_optimization_metadata failed: {exc}')
    try:
        surrogate_metadata = list(recorded_data.list_surrogate_metadata(workspace))
    except Exception as exc:
        surrogate_metadata = []
        issues.append(f'list_surrogate_metadata failed: {exc}')
    try:
        normalized = {str(name): tuple((float(value) for value in values)) for name, values in recorded_data.get_normalized_variables(workspace, status=None)}
    except Exception as exc:
        normalized = {}
        issues.append(f'get_normalized_variables failed: {exc}')
    loaded = (
        attempt, workspace, issues, rows, objectives, cost_view_summary,
        records, optimization_metadata, surrogate_metadata, normalized,
    )
    return result, loaded


def _collect_cell(spec: Mapping[str, Any], cell_plan: Mapping[str, Any], cell_state: Mapping[str, Any], evidence_dir: Path) -> dict[str, Any]:
    from .storage import json_safe as _json_safe
    result, loaded = _load_cell_public_data(cell_plan, cell_state)
    if loaded is None:
        return result
    (
        attempt, workspace, issues, rows, objectives, cost_view_summary,
        records, optimization_metadata, surrogate_metadata, normalized,
    ) = loaded
    generations = _generation_metadata(optimization_metadata)
    attempted = _attempted_count(generations) if cell_plan['kind'] == 'measured' else len(records)
    attempted_source = 'sum of population_size in public generation metadata' if cell_plan['kind'] == 'measured' else 'public record count in the disposable smoke workspace'
    initial_fingerprint, initial_count, initial_reason = _initial_population_fingerprint(generations, normalized, records)
    finite_rows = [row for row in rows if _finite_cost_row(row)]
    invalid_rows = len(rows) - len(finite_rows)
    generation_validity: list[dict[str, Any]] = []
    for item in generations:
        generation_index = int(item.get('generation_index', 0) or 0)
        generation_rows = [row for row in rows if row.get('generation_index') == generation_index]
        finite_generation_rows = [row for row in generation_rows if _finite_cost_row(row)]
        generation_validity.append({'generation_index': generation_index, 'population_size': item.get('population_size'), 'source': item.get('source'), 'surrogate_used': item.get('surrogate_used'), 'completed_rows': len(generation_rows), 'finite_rows': len(finite_generation_rows), 'all_infinite': bool(generation_rows and (not finite_generation_rows))})
    hypervolume: dict[str, Any]
    if rows:
        try:
            x_values, cumulative, current, reference = cost_viewer.hypervolume_series(rows)
            attempted_by_generation: list[int] = []
            running = 0
            for item in generations:
                running += _attempted_count([item])
                attempted_by_generation.append(running)
            cumulative_values = [float(value) for value in cumulative]
            current_values = [float(value) for value in current]
            if len(attempted_by_generation) != len(cumulative_values):
                issues.append('hypervolume generation count differs from public optimization metadata; attempted-count alignment is unavailable')
                attempted_axis: list[int] | None = None
            else:
                attempted_axis = attempted_by_generation
            hypervolume = {'completed_row_axis': [float(value) for value in x_values], 'attempted_evaluation_axis': attempted_axis, 'cumulative': cumulative_values, 'current_generation': current_values, 'reference_point': [float(value) for value in reference], 'final_cumulative': cumulative_values[-1] if cumulative_values else None}
        except Exception as exc:
            hypervolume = {'final_cumulative': None, 'error': str(exc)}
            issues.append(f'hypervolume_series failed: {exc}')
    else:
        hypervolume = {'final_cumulative': None, 'error': 'no completed cost rows'}
    try:
        observed_shapes, shape_error = _rawdata_shapes(workspace, records)
        if shape_error:
            issues.append(shape_error)
    except Exception as exc:
        observed_shapes = {}
        issues.append(f'rawData shape inspection failed: {exc}')
    expected_shapes = spec['cases'][cell_plan['case']]['rawdata_shapes']
    rawdata_shape_match = bool(observed_shapes) and observed_shapes == expected_shapes
    evaluator_duration = sum((float(item.get('job_metadata', {}).get('elapsed_time', 0.0)) for item in records if isinstance(item.get('job_metadata', {}).get('elapsed_time'), (int, float))))
    training_events = [{key: item.get(key) for key in ('generation_index', 'duration_sec', 'sample_count', 'query_count', 'epochs', 'member_count', 'device') if key in item} for item in surrogate_metadata if isinstance(item, Mapping)]
    training_duration = sum((float(item['duration_sec']) for item in surrogate_metadata if isinstance(item, Mapping) and isinstance(item.get('duration_sec'), (int, float))))
    reference_generation_sec = spec['cases'][cell_plan['case']].get('representative_expensive_generation_sec')
    surrogate_evidence: dict[str, Any] | None = None
    is_surrogate = bool(cell_plan['kind'] == 'measured' and spec['arms'].get(cell_plan['arm'], {}).get('surrogate', False))
    if is_surrogate:
        python = str(spec['package']['python'])
        summary = _capture_json_cli([python, '-m', 'yadof', 'view', 'surrogate', 'summary', '--workspace', str(workspace), '--format', 'json'], cwd=workspace, evidence_dir=evidence_dir, stem=f"{cell_plan['cell_id']}.surrogate-summary", timeout=300)
        checkpoint_count = None
        if isinstance(summary['payload'], Mapping):
            checkpoint_count = summary['payload'].get('checkpoint_count', len(summary['payload'].get('checkpoints', [])))
        public_training_checkpoint_count = sum((1 for item in surrogate_metadata if isinstance(item, Mapping) and item.get('status') == 'completed' and (not bool(item.get('skipped', False))) and bool(item.get('checkpoint_path'))))
        effective_checkpoint_count = checkpoint_count if isinstance(checkpoint_count, int) else public_training_checkpoint_count
        audits: dict[str, Any] = {}
        if effective_checkpoint_count > 0:
            for quantity, stem_suffix in (('all-costs', 'costs'), ('all-rawdata', 'rawdata')):
                audit = _capture_json_cli([python, '-m', 'yadof', 'view', 'surrogate', 'audit', '--workspace', str(workspace), '--sample-percent', str(spec['runner']['audit_sample_percent']), '--random-seed', str(spec['runner']['audit_random_seed']), '--metric', 'both', '--quantity', quantity, '--format', 'json'], cwd=workspace, evidence_dir=evidence_dir, stem=f"{cell_plan['cell_id']}.surrogate-audit-{stem_suffix}", timeout=int(spec['runner']['command_timeout_sec']))
                audits[stem_suffix] = {'returncode': audit['metadata']['returncode'], 'payload': audit['payload'], 'command': audit['metadata']}
        surrogate_evidence = {'checkpoint_count': effective_checkpoint_count, 'checkpoint_count_source': 'view surrogate summary JSON' if isinstance(checkpoint_count, int) else 'public list_surrogate_metadata fallback because summary JSON failed', 'summary_checkpoint_count': checkpoint_count, 'public_training_checkpoint_count': public_training_checkpoint_count, 'summary': summary['payload'], 'summary_command': summary['metadata'], 'audits': audits, 'training_events': training_events, 'training_duration_sec': training_duration, 'representative_expensive_generation_context': {'declared_generation_sec': float(reference_generation_sec), 'training_headroom_sec': float(reference_generation_sec) - training_duration, 'training_fraction_of_declared_generation': training_duration / float(reference_generation_sec), 'interpretation': 'Context only; not an algorithm verdict or a comparison to this cheap run.'} if isinstance(reference_generation_sec, (int, float)) and float(reference_generation_sec) > 0 else None, 'training_lag_generations': {'value': None, 'reason': "The public summary/audit schema does not expose each checkpoint's exact training cutoff."}, 'coverage_classification': {'value': None, 'reason': 'Without a public checkpoint cutoff, overlap and forward-generation audit cells are not relabeled.'}}
    status_counts = {str(status): sum((1 for item in records if str(item.get('status')) == str(status))) for status in {item.get('status') for item in records}}
    completed_evaluations = int(status_counts.get('completed', 0))
    failed_evaluations = max(0, attempted - completed_evaluations)
    timeout_evaluations = sum((1 for item in records if 'timeout' in json.dumps({'status': item.get('status'), 'error': item.get('error'), 'job_metadata': item.get('job_metadata', {})}, default=str, ensure_ascii=False).casefold()))
    command_validity = _command_validity(attempt)
    workspace_roots = {root: (workspace / root).is_dir() for root in ('submit', 'job_template')}
    result['validity'] = {'planned_real_evaluations': int(cell_plan['planned_attempted_evaluations']), 'attempted_real_evaluations': attempted, 'completed_candidate_evaluations': completed_evaluations, 'failed_candidate_evaluations': failed_evaluations, 'timeout_candidate_evaluations': timeout_evaluations, 'all_infinite_generation_count': sum((1 for item in generation_validity if item['all_infinite'])), 'generation_sequence': generation_validity, 'complete_task_roots': workspace_roots, 'command_evidence': command_validity['commands'], 'yadof_check_warnings': command_validity['yadof_check_warnings']}
    metrics = {'objective_names': objectives, 'objective_count': len(objectives), 'completed_cost_rows': len(rows), 'finite_objective_rows': len(finite_rows), 'invalid_objective_rows': invalid_rows, 'attempted_real_evaluations': attempted, 'attempted_count_source': attempted_source, 'record_status_counts': dict(sorted(status_counts.items())), 'evaluator_elapsed_sec_sum': evaluator_duration, 'initial_population_fingerprint': initial_fingerprint, 'initial_population_count': initial_count, 'initial_population_gap': initial_reason, 'hypervolume': hypervolume, 'cost_view_summary': cost_view_summary, 'evaluation_normalized_hv_auc': {'value': None, 'reason': 'The public yadof cost_viewer exposes HV series but no evaluation-normalized HV-AUC contract.'}, 'rawdata_shapes': observed_shapes, 'rawdata_shapes_match_contract': rawdata_shape_match, 'generation_metadata': optimization_metadata, 'surrogate_training_metadata': surrogate_metadata, 'surrogate': surrogate_evidence, 'cost_rows': rows}
    complete = cell_state['status'] == 'completed'
    result['eligible_for_primary_performance_aggregate'] = bool(complete and cell_plan['kind'] == 'measured')
    if not complete:
        result['exclusion_reason'] = 'cell execution did not complete'
    elif cell_plan['kind'] != 'measured':
        result['exclusion_reason'] = 'disposable smoke cells are structural evidence, not measured arms'
    result['metrics'] = _json_safe(metrics)
    result['public_api_issues'] = issues
    return _json_safe(result)

def collect_run(paths: Paths, run_id: str) -> tuple[Path, dict[str, Any]]:
    from .state import load_run, verify_run_inputs
    from .storage import json_safe as _json_safe, new_sequence_dir as _new_sequence_dir, atomic_write_json, file_sha256, utc_now, write_new_json
    run_root, spec, state = load_run(paths, run_id)
    verify_run_inputs(paths, run_root, spec, verify_automation=False, verify_config=False)
    evidence_dir = _new_sequence_dir(run_root / 'evidence', 'collect')
    cell_plan_by_id = {cell['cell_id']: cell for cell in spec['plan']['cells']}
    cells: dict[str, Any] = {}
    for cell_id, cell_state in state['cells'].items():
        cells[cell_id] = _collect_cell(spec, cell_plan_by_id[cell_id], cell_state, evidence_dir)
    tool_gaps: dict[str, str] = {'evaluation_normalized_hv_auc': 'No public yadof metric contract; values are null.', 'checkpoint_training_cutoff': 'Not present in public surrogate summary/audit JSON; overlap/forward labels are withheld.'}
    failed_summaries = [cell_id for cell_id, cell in cells.items() if _metric(cell, 'surrogate', 'summary_command', 'returncode') not in (None, 0)]
    if failed_summaries:
        tool_gaps['surrogate_summary_json'] = f"The public `yadof view surrogate summary --format json` command failed for {failed_summaries}; its append-only stderr evidence is retained. On the first test_com canary, yadof 0.4.0 reported `could not convert string to float: 'x0'`."
    failed_audits = [cell_id for cell_id, cell in cells.items() if any((value.get('returncode') not in (None, 0) for value in (_metric(cell, 'surrogate', 'audits') or {}).values()))]
    if failed_audits:
        tool_gaps['surrogate_audit_json'] = f'The public surrogate audit JSON command failed for {failed_audits}; command metadata and stderr are retained without private fallback.'
    collection = {'schema_version': SCHEMA_VERSION, 'run_id': run_id, 'spec_sha256': spec['spec_sha256'], 'collected_utc': utc_now(), 'execution_state': state['status'], 'suite': spec['suite'], 'purpose': spec['purpose'], 'collector': _collector_identity(), 'cells': cells, 'tool_gaps': tool_gaps}
    collection_path = evidence_dir / 'collection.json'
    write_new_json(collection_path, _json_safe(collection))
    atomic_write_json(run_root / 'metrics.json', _json_safe(collection))
    atomic_write_json(run_root / 'collection_index.json', {'schema_version': SCHEMA_VERSION, 'latest': str(collection_path.relative_to(run_root)), 'sha256': file_sha256(collection_path), 'updated_utc': utc_now()})
    return (collection_path, collection)

def _latest_collection(run_root: Path) -> tuple[Path, dict[str, Any]]:
    from .storage import read_json, resolve_inside
    index = read_json(run_root / 'collection_index.json')
    path = resolve_inside(run_root, str(index.get('latest', '')), label='collection index')
    if not path.is_file():
        raise BenchmarkError(f'indexed collection does not exist: {path}')
    return (path, read_json(path))

def _metric(cell: Mapping[str, Any], *keys: str) -> Any:
    value: Any = cell.get('metrics')
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value

def _population_pair_rows(spec: Mapping[str, Any], collection: Mapping[str, Any]) -> list[dict[str, Any]]:
    measured = [cell for cell in collection['cells'].values() if cell.get('kind') == 'measured']
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for cell in measured:
        groups[str(cell['case']), int(cell['seed'])].append(cell)
    rows: list[dict[str, Any]] = []
    expected_arms = list(spec['arms'])
    for (case_id, seed), cells in sorted(groups.items()):
        by_arm = {str(cell['arm']): cell for cell in cells}
        fingerprints = {arm: _metric(by_arm[arm], 'initial_population_fingerprint') for arm in expected_arms if arm in by_arm}
        available = len(fingerprints) == len(expected_arms) and all(fingerprints.values())
        rows.append({'case': case_id, 'seed': seed, 'fingerprints': fingerprints, 'equal': bool(available and len(set(fingerprints.values())) == 1), 'gap': None if available else 'one or more arm fingerprints are unavailable'})
    return rows

def _structural_report(spec: Mapping[str, Any], collection: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    workspace_paths: list[str] = []
    for cell_id, cell in collection['cells'].items():
        complete = cell.get('execution_status') == 'completed'
        checks.append({'check': 'cell-completed', 'cell_id': cell_id, 'ok': complete, 'details': cell.get('exclusion_reason')})
        if complete:
            workspace_paths.append(str(cell.get('attempt', {}).get('workspace')))
            expected_objectives = int(spec['cases'][cell['case']]['expected_objectives'])
            actual_objectives = _metric(cell, 'objective_count')
            checks.append({'check': 'objective-count', 'cell_id': cell_id, 'ok': actual_objectives == expected_objectives, 'details': {'expected': expected_objectives, 'actual': actual_objectives}})
            checks.append({'check': 'rawdata-shape-contract', 'cell_id': cell_id, 'ok': bool(_metric(cell, 'rawdata_shapes_match_contract')), 'details': _metric(cell, 'rawdata_shapes')})
            checks.append({'check': 'declared-inputs-unchanged', 'cell_id': cell_id, 'ok': bool(cell.get('attempt', {}).get('input_unchanged')), 'details': cell.get('attempt')})
            warnings = cell.get('validity', {}).get('yadof_check_warnings', [])
            checks.append({'check': 'yadof-check-zero-warnings', 'cell_id': cell_id, 'ok': not warnings, 'details': warnings})
            roots = cell.get('validity', {}).get('complete_task_roots', {})
            checks.append({'check': 'complete-task-source-roots', 'cell_id': cell_id, 'ok': bool(roots) and all((bool(value) for value in roots.values())), 'details': roots})
            if cell.get('kind') == 'measured':
                generations = cell.get('validity', {}).get('generation_sequence', [])
                expected_count = int(next((plan_cell['generations'] for plan_cell in spec['plan']['cells'] if plan_cell['cell_id'] == cell_id)))
                indices = [item.get('generation_index') for item in generations]
                expected_indices = list(range(expected_count))
                checks.append({'check': 'expected-generation-sequence', 'cell_id': cell_id, 'ok': indices[:expected_count] == expected_indices, 'details': {'expected_prefix': expected_indices, 'actual': indices}})
                checks.append({'check': 'finite-cost-in-each-expected-generation', 'cell_id': cell_id, 'ok': len(generations) >= expected_count and all((int(item.get('finite_rows', 0)) > 0 for item in generations[:expected_count])), 'details': generations})
                surrogate_arm = bool(spec['arms'][cell['arm']]['surrogate'])
                surrogate_used = [item.get('surrogate_used') for item in generations]
                intended = any((value is True for value in surrogate_used)) if surrogate_arm else not any((value is True for value in surrogate_used))
                checks.append({'check': 'optimization-metadata-arm', 'cell_id': cell_id, 'ok': intended, 'details': {'arm': cell['arm'], 'surrogate_expected': surrogate_arm, 'surrogate_used': surrogate_used, 'sources': [item.get('source') for item in generations]}})
            if cell.get('kind') == 'measured' and spec['arms'][cell['arm']]['surrogate']:
                checkpoint_count = _metric(cell, 'surrogate', 'checkpoint_count')
                checks.append({'check': 'surrogate-checkpoint-created', 'cell_id': cell_id, 'ok': isinstance(checkpoint_count, int) and checkpoint_count > 0, 'details': {'checkpoint_count': checkpoint_count}})
                audits = _metric(cell, 'surrogate', 'audits') or {}
                audit_details = {name: {'returncode': value.get('returncode'), 'payload_present': value.get('payload') is not None} for name, value in audits.items()}
                checks.append({'check': 'surrogate-summary-and-audit-json', 'cell_id': cell_id, 'ok': _metric(cell, 'surrogate', 'summary') is not None and {'costs', 'rawdata'}.issubset(audits) and all((value.get('returncode') == 0 and value.get('payload') is not None for value in audits.values())), 'details': audit_details})
    population_pairs = _population_pair_rows(spec, collection)
    for pair in population_pairs:
        checks.append({'check': 'paired-generation-zero-population', 'cell_id': f"{pair['case']}__seed-{pair['seed']}", 'ok': pair['equal'], 'details': pair})
    checks.append({'check': 'isolated-cell-workspaces', 'cell_id': 'selected-matrix', 'ok': len(workspace_paths) == len(set(workspace_paths)), 'details': workspace_paths})
    return {'contract_satisfied': all((bool(item['ok']) for item in checks)), 'checks': checks, 'initial_population_pairs': population_pairs}

def _descriptive(values: Sequence[float]) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {'count': 0, 'mean': None, 'median': None, 'minimum': None, 'maximum': None}
    return {'count': len(finite), 'mean': statistics.fmean(finite), 'median': statistics.median(finite), 'minimum': min(finite), 'maximum': max(finite)}

def _performance_report(spec: Mapping[str, Any], collection: Mapping[str, Any]) -> dict[str, Any]:
    surrogate_arms = [arm for arm, details in spec['arms'].items() if details.get('surrogate')]
    real_arms = [arm for arm, details in spec['arms'].items() if not details.get('surrogate')]
    if len(surrogate_arms) != 1 or len(real_arms) != 1:
        raise BenchmarkError('descriptive paired report requires exactly one surrogate and one non-surrogate arm')
    surrogate_arm = surrogate_arms[0]
    real_arm = real_arms[0]
    measured = [cell for cell in collection['cells'].values() if cell.get('kind') == 'measured']
    groups: dict[tuple[str, int], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for cell in measured:
        groups[str(cell['case']), int(cell['seed'])][str(cell['arm'])] = cell
    pair_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    difference_fields = {'final_cumulative_hypervolume': ('hypervolume', 'final_cumulative'), 'evaluator_elapsed_sec_sum': ('evaluator_elapsed_sec_sum',), 'finite_objective_rows': ('finite_objective_rows',), 'invalid_objective_rows': ('invalid_objective_rows',)}
    for (case_id, seed), by_arm in sorted(groups.items()):
        real = by_arm.get(real_arm)
        surrogate = by_arm.get(surrogate_arm)
        reasons: list[str] = []
        if real is None or surrogate is None:
            reasons.append('paired arm is missing')
        elif not real.get('eligible_for_primary_performance_aggregate') or not surrogate.get('eligible_for_primary_performance_aggregate'):
            reasons.append('one or both cells are incomplete')
        fingerprints = {real_arm: _metric(real or {}, 'initial_population_fingerprint'), surrogate_arm: _metric(surrogate or {}, 'initial_population_fingerprint')}
        fingerprint_equal = bool(all(fingerprints.values()) and len(set(fingerprints.values())) == 1)
        if not fingerprint_equal:
            reasons.append('generation-0 population fingerprints do not match')
        attempted = {real_arm: _metric(real or {}, 'attempted_real_evaluations'), surrogate_arm: _metric(surrogate or {}, 'attempted_real_evaluations')}
        if attempted[real_arm] != attempted[surrogate_arm]:
            reasons.append('observed attempted real-evaluation counts are unequal')
        if reasons:
            excluded.append({'case': case_id, 'seed': seed, 'reasons': reasons, 'execution_status': {real_arm: real.get('execution_status') if real else None, surrogate_arm: surrogate.get('execution_status') if surrogate else None}, 'attempted_real_evaluations': attempted, 'initial_population_fingerprints': fingerprints})
            continue
        assert real is not None and surrogate is not None
        raw: dict[str, Any] = {}
        differences: dict[str, Any] = {}
        for name, keys in difference_fields.items():
            real_value = _metric(real, *keys)
            surrogate_value = _metric(surrogate, *keys)
            raw[name] = {real_arm: real_value, surrogate_arm: surrogate_value}
            if isinstance(real_value, (int, float)) and isinstance(surrogate_value, (int, float)):
                differences[f'{surrogate_arm}_minus_{real_arm}'] = differences.get(f'{surrogate_arm}_minus_{real_arm}', {})
                differences[f'{surrogate_arm}_minus_{real_arm}'][name] = float(surrogate_value) - float(real_value)
        raw['surrogate_training_duration_sec'] = _metric(surrogate, 'surrogate', 'training_duration_sec')
        raw['evaluation_normalized_hv_auc'] = {real_arm: _metric(real, 'evaluation_normalized_hv_auc', 'value'), surrogate_arm: _metric(surrogate, 'evaluation_normalized_hv_auc', 'value')}
        pair_rows.append({'case': case_id, 'seed': seed, 'attempted_real_evaluations': attempted, 'initial_population_fingerprints': fingerprints, 'raw': raw, 'differences': differences})
    aggregate: dict[str, Any] = {}
    for case_id in sorted({row['case'] for row in pair_rows}):
        case_rows = [row for row in pair_rows if row['case'] == case_id]
        metrics: dict[str, list[float]] = defaultdict(list)
        for row in case_rows:
            for direction, values in row['differences'].items():
                for name, value in values.items():
                    metrics[f'{direction}.{name}'].append(float(value))
        aggregate[case_id] = {name: _descriptive(values) for name, values in sorted(metrics.items())}
    return {'interpretation_policy': 'Raw values and paired descriptive differences only; no ordering, inferential test, decision threshold, or scientific acceptance claim is produced.', 'arm_roles': {'real': real_arm, 'surrogate': surrogate_arm}, 'arm_labels': {real_arm: str(spec['arms'][real_arm].get('display_name', real_arm)), surrogate_arm: str(spec['arms'][surrogate_arm].get('display_name', surrogate_arm))}, 'included_pairs': pair_rows, 'excluded_pairs_retained': excluded, 'descriptive_aggregate_by_case': aggregate, 'tool_gaps': collection.get('tool_gaps', {})}

def _format_value(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, float):
        return f'{value:.8g}'
    return str(value)

def _markdown_cell(value: Any) -> str:
    return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')

def format_hypervolume_table(report: Mapping[str, Any]) -> str | None:
    """Return the compact final cumulative-HV table used by CLI and Markdown."""
    if report.get('purpose') != 'performance':
        return None
    performance = report.get('performance', {})
    real_arm = performance.get('arm_roles', {}).get('real')
    surrogate_arm = performance.get('arm_roles', {}).get('surrogate')
    if not real_arm or not surrogate_arm:
        return None
    labels = performance.get('arm_labels', {})
    real_label = _markdown_cell(labels.get(real_arm, real_arm))
    surrogate_label = _markdown_cell(labels.get(surrogate_arm, surrogate_arm))
    lines = ['Final cumulative hypervolume:', '', f'| Case | Seed | {real_label} | {surrogate_label} |', '|---|---:|---:|---:|']
    for row in performance.get('included_pairs', []):
        raw = row.get('raw', {}).get('final_cumulative_hypervolume', {})
        lines.append(f"| {_markdown_cell(row.get('case'))} | {_markdown_cell(row.get('seed'))} | {_format_value(raw.get(real_arm))} | {_format_value(raw.get(surrogate_arm))} |")
    return '\n'.join(lines)

def _report_markdown(report: Mapping[str, Any]) -> str:
    lines = [f"# Benchmark report: {report['run_id']}", '', f"- Suite: `{report['suite']}`", f"- Purpose: `{report['purpose']}`", f"- Generated: `{report['generated_utc']}`", f"- Collection: `{report['collection']}`", '']
    if report['purpose'] == 'structural':
        structural = report['structural']
        lines.extend(['## Structural contract', '', f"Contract satisfied: `{str(structural['contract_satisfied']).lower()}`", '', '| Check | Cell | Result |', '|---|---|---|'])
        for item in structural['checks']:
            lines.append(f"| {item['check']} | `{item['cell_id']}` | {('ok' if item['ok'] else 'not satisfied')} |")
    else:
        performance = report['performance']
        lines.extend(['## Descriptive paired output', '', performance['interpretation_policy'], ''])
        table = format_hypervolume_table(report)
        if table is not None:
            lines.extend(table.splitlines())
        lines.extend(['', f"Excluded paired cells retained in raw evidence: {len(performance['excluded_pairs_retained'])}."])
    lines.extend(['', '## Public-tool gaps', ''])
    for name, reason in report.get('tool_gaps', {}).items():
        lines.append(f'- `{name}`: {reason}')
    return '\n'.join(lines) + '\n'

def report_run(paths: Paths, run_id: str) -> tuple[Path, Path, dict[str, Any]]:
    from .state import load_run, verify_run_inputs
    from .storage import json_safe as _json_safe, new_sequence_dir as _new_sequence_dir, write_new_text as _write_new_text, atomic_write_json, atomic_write_text, file_sha256, utc_now, write_new_json
    run_root, spec, _state = load_run(paths, run_id)
    verify_run_inputs(paths, run_root, spec, verify_automation=False, verify_config=False)
    collection_path, collection = _latest_collection(run_root)
    report: dict[str, Any] = {'schema_version': SCHEMA_VERSION, 'run_id': run_id, 'suite': spec['suite'], 'purpose': spec['purpose'], 'generated_utc': utc_now(), 'spec_sha256': spec['spec_sha256'], 'collection': str(collection_path.relative_to(run_root)), 'collection_sha256': file_sha256(collection_path), 'collector': collection.get('collector'), 'tool_gaps': collection.get('tool_gaps', {}), 'validity_by_cell': {cell_id: {'execution_status': cell.get('execution_status'), 'exclusion_reason': cell.get('exclusion_reason'), 'validity': cell.get('validity'), 'public_api_issues': cell.get('public_api_issues', [])} for cell_id, cell in collection['cells'].items()}}
    if spec['purpose'] == 'structural':
        report['structural'] = _structural_report(spec, collection)
    else:
        report['performance'] = _performance_report(spec, collection)
    report_dir = _new_sequence_dir(run_root / 'reports', 'report')
    json_path = report_dir / 'report.json'
    markdown_path = report_dir / 'report.md'
    write_new_json(json_path, _json_safe(report))
    markdown = _report_markdown(report)
    _write_new_text(markdown_path, markdown)
    atomic_write_json(run_root / 'report.json', _json_safe(report))
    atomic_write_text(run_root / 'report.md', markdown)
    atomic_write_json(run_root / 'report_index.json', {'schema_version': SCHEMA_VERSION, 'latest_json': str(json_path.relative_to(run_root)), 'latest_markdown': str(markdown_path.relative_to(run_root)), 'json_sha256': file_sha256(json_path), 'markdown_sha256': file_sha256(markdown_path), 'updated_utc': utc_now()})
    return (json_path, markdown_path, report)

def summarize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return bounded validity and result evidence without fingerprints or raw rows."""
    from .storage import json_safe as _json_safe
    status_counts: dict[str, int] = defaultdict(int)
    evaluation_totals = {'planned': 0, 'attempted': 0, 'completed': 0, 'failed': 0, 'timeouts': 0, 'all_infinite_generations': 0}
    attention: list[dict[str, Any]] = []
    validity_keys = {'planned': 'planned_real_evaluations', 'attempted': 'attempted_real_evaluations', 'completed': 'completed_candidate_evaluations', 'failed': 'failed_candidate_evaluations', 'timeouts': 'timeout_candidate_evaluations', 'all_infinite_generations': 'all_infinite_generation_count'}
    for cell_id, cell in report.get('validity_by_cell', {}).items():
        status = str(cell.get('execution_status', 'unknown'))
        status_counts[status] += 1
        validity = cell.get('validity') or {}
        for summary_key, source_key in validity_keys.items():
            value = validity.get(source_key)
            if isinstance(value, (int, float)):
                evaluation_totals[summary_key] += int(value)
        issues = list(cell.get('public_api_issues') or [])
        concerns: list[str] = []
        if status != 'completed':
            concerns.append(f'execution_status={status}')
        for source_key, label in (('failed_candidate_evaluations', 'failed candidates'), ('timeout_candidate_evaluations', 'candidate timeouts'), ('all_infinite_generation_count', 'all-infinite generations')):
            count = int(validity.get(source_key, 0) or 0)
            if count:
                concerns.append(f'{count} {label}')
        warnings = list(validity.get('yadof_check_warnings') or [])
        if warnings:
            concerns.append(f'{len(warnings)} yadof check warnings')
        if issues:
            concerns.append(f'{len(issues)} public API issues')
        if concerns:
            attention.append({'cell_id': cell_id, 'concerns': concerns, 'exclusion_reason': cell.get('exclusion_reason'), 'public_api_issues': issues})
    summary: dict[str, Any] = {'schema_version': report.get('schema_version', SCHEMA_VERSION), 'view': 'report-summary', 'run_id': report.get('run_id'), 'suite': report.get('suite'), 'purpose': report.get('purpose'), 'generated_utc': report.get('generated_utc'), 'validity': {'cells_by_execution_status': dict(sorted(status_counts.items())), 'evaluation_totals': evaluation_totals, 'attention': attention}, 'tool_gaps': report.get('tool_gaps', {})}
    if report.get('purpose') == 'structural':
        structural = report.get('structural', {})
        failed_checks = [{'check': item.get('check'), 'cell_id': item.get('cell_id')} for item in structural.get('checks', []) if not item.get('ok')]
        summary['structural'] = {'contract_satisfied': bool(structural.get('contract_satisfied')), 'check_count': len(structural.get('checks', [])), 'failed_checks': failed_checks}
    else:
        performance = report.get('performance', {})
        real_arm = performance.get('arm_roles', {}).get('real')
        surrogate_arm = performance.get('arm_roles', {}).get('surrogate')
        difference_key = f'{surrogate_arm}_minus_{real_arm}'
        pairs: list[dict[str, Any]] = []
        for row in performance.get('included_pairs', []):
            raw = row.get('raw', {})
            differences = row.get('differences', {}).get(difference_key, {})
            metrics: dict[str, Any] = {}
            for metric in ('final_cumulative_hypervolume', 'evaluator_elapsed_sec_sum'):
                if metric in raw:
                    metrics[metric] = {'by_arm': raw.get(metric), 'surrogate_minus_real': differences.get(metric)}
            metrics['surrogate_training_duration_sec'] = raw.get('surrogate_training_duration_sec')
            pairs.append({'case': row.get('case'), 'seed': row.get('seed'), 'attempted_real_evaluations': row.get('attempted_real_evaluations'), 'metrics': metrics})
        aggregate = {case_id: {name: values for name, values in metrics.items() if name.endswith('.final_cumulative_hypervolume') or name.endswith('.evaluator_elapsed_sec_sum')} for case_id, metrics in performance.get('descriptive_aggregate_by_case', {}).items()}
        summary['performance'] = {'interpretation_policy': performance.get('interpretation_policy'), 'arm_roles': performance.get('arm_roles', {}), 'arm_labels': performance.get('arm_labels', {}), 'included_pair_count': len(pairs), 'excluded_pair_count': len(performance.get('excluded_pairs_retained', [])), 'pairs': pairs, 'excluded_pairs': performance.get('excluded_pairs_retained', []), 'descriptive_aggregate_by_case': aggregate}
    return _json_safe(summary)

def _artifact_entry(path: Path, role: str, read_policy: str) -> dict[str, Any]:
    exists = path.is_file()
    return {'role': role, 'path': str(path), 'exists': exists, 'size_bytes': path.stat().st_size if exists else None, 'read_policy': read_policy}

def inspect_run(paths: Paths, run_id: str) -> dict[str, Any]:
    """Build the bounded first-read view for an existing run."""
    from .state import load_run
    from .storage import json_safe as _json_safe, read_json
    from .timing import estimate_run_timing, summarize_run_state
    run_root, spec, state = load_run(paths, run_id)
    report_markdown = run_root / 'report.md'
    report_json = run_root / 'report.json'
    metrics_json = run_root / 'metrics.json'
    timing = estimate_run_timing(spec, state, run_root=run_root)
    run_summary = summarize_run_state(run_root, run_id, state, timing=timing)
    run_summary.pop('schema_version', None)
    run_summary.pop('view', None)
    results = summarize_report(read_json(report_json)) if report_json.is_file() else None
    artifacts = [_artifact_entry(report_markdown, 'concise human/agent report', 'read first when the structured summary needs narrative context'), _artifact_entry(report_json, 'complete stable report', 'query targeted fields only; do not repeatedly read the whole file'), _artifact_entry(metrics_json, 'large collected public-API evidence', 'never read whole; query one cell and field only after the report is insufficient'), _artifact_entry(run_root / 'run_state.json', 'execution state and attempt index', 'query a specific non-completed cell during diagnosis'), _artifact_entry(run_root / 'run_spec.json', 'immutable provenance', 'read only when verifying identity or reproducing a run'), _artifact_entry(run_root / 'matrix.json', 'expanded immutable cell matrix', 'read only when one planned cell or command must be verified'), _artifact_entry(run_root / TIMING_HISTORY_NAME, 'bounded cross-run timing prior snapshot', 'read only when diagnosing ETA basis, sample count, or dispersion')]
    if results is not None:
        next_commands: list[list[str]] = []
    elif metrics_json.is_file():
        next_commands = [['--runs-dir', str(paths.runs), 'report', '--run-id', run_id]]
    elif state.get('status') == 'completed':
        next_commands = [['--runs-dir', str(paths.runs), 'collect', '--run-id', run_id]]
    else:
        next_commands = [['--runs-dir', str(paths.runs), 'collect', '--run-id', run_id], ['--runs-dir', str(paths.runs), 'resume', '--run-id', run_id]]
    return _json_safe({'schema_version': SCHEMA_VERSION, 'view': 'agent-summary', 'run': {**run_summary, 'suite': spec.get('suite'), 'purpose': spec.get('purpose')}, 'results': results, 'artifacts': artifacts, 'next_commands': next_commands, 'progressive_disclosure': 'Use this summary first, then report.md, then targeted report.json fields. Read one cell/log only for diagnosis; never load metrics.json wholesale.'})


generation_metadata = _generation_metadata
