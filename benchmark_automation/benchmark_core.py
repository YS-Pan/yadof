"""Compatibility facade for the split benchmark runtime."""
from __future__ import annotations
import datetime as dt
import importlib
import importlib.util
from pathlib import Path
import sys
import uuid
_BASE = f"{__package__ + '.' if __package__ else ''}benchmark_runtime"
_EXPORTS = {'contracts': ['BenchmarkError', 'Paths'], 'progress': ['_AsciiBarColumn', '_parse_yadof_progress', 'CellProgress'], 'storage': ['utc_now', 'canonical_json', 'object_sha256', 'file_sha256', 'atomic_write_json', 'atomic_write_text', 'write_new_json', 'read_json', '_baseline_identity', 'resolve_inside', 'resolve_runs_dir', '_is_within', '_paths_overlap', '_existing_disk_root', '_declared_files', 'task_manifest', 'task_fingerprint', 'directory_manifest', 'directory_fingerprint', '_load_toml', '_json_safe', '_new_sequence_dir', '_write_new_text'], 'planning': ['load_config', 'validate_config', '_safe_id', '_config_overrides', '_cell_id', '_select_values', '_cost_view_command', '_postprocess_command', '_visualization_file_prefix', '_baseline_visualization_directory_name', '_planned_commands', 'build_plan', '_package_identity', '_baseline_details', '_strategy_details', '_run_read_only', 'preflight', 'build_run_spec', 'make_run_id', 'summarize_plan', '_tail_text', 'summarize_preflight'], 'state': ['_initial_state', 'create_run', 'load_run', 'verify_run_inputs', '_save_state', '_copy_declared_inputs', '_apply_config_overrides', '_copy_history_snapshot', '_attempt_directory', '_prepare_attempt', '_materialize_attempt_inputs'], 'execution': ['_stream_pipe', '_render_stream_events', '_execute_logged', '_completed_generation_indices', '_has_completed_generation_prefix', '_surrogate_has_been_used', '_cell_command', '_seal_attempt', '_run_one_cell', 'execute_run'], 'results': ['_capture_json_cli', '_generation_metadata', '_attempted_count', '_initial_population_fingerprint', '_rawdata_shapes', '_command_validity', '_finite_cost_row', '_collect_cell', 'collect_run', '_latest_collection', '_metric', '_population_pair_rows', '_structural_report', '_descriptive', '_performance_report', '_format_value', '_markdown_cell', 'format_hypervolume_table', '_report_markdown', 'report_run', 'summarize_report', '_artifact_entry', 'inspect_run'], 'timing': ['_parse_utc', '_format_utc', '_attempt_duration_sec', '_timing_signature_payload', '_timing_signatures', '_snapshot_cross_run_timing', '_load_timing_history', '_duration_observations', '_cell_duration_estimate', '_tail_yadof_progress', '_tail_progress_events', '_active_command', '_generation_phase_estimate', 'estimate_run_timing', 'summarize_run_state']}
for _module_name, _names in _EXPORTS.items():
    _module = importlib.import_module(f"{_BASE}.{_module_name}")
    for _name in _names:
        globals()[_name] = getattr(_module, _name)
_contracts = importlib.import_module(f"{_BASE}.contracts")
for _name in _contracts.__all__:
    globals()[_name] = getattr(_contracts, _name)
def _snapshot_execution_module(run_root: Path, spec: dict):
    snapshot = run_root / spec.get("automation", {}).get(
        "execution_snapshot", "inputs/execution/benchmark_runtime"
    )
    if not (snapshot / "__init__.py").is_file():
        raise BenchmarkError(
            "unfinished run has no complete execution snapshot; choose an explicit restart or migration"
        )
    package_name = f"_benchmark_execution_{uuid.uuid4().hex}"
    package_spec = importlib.util.spec_from_file_location(
        package_name,
        snapshot / "__init__.py",
        submodule_search_locations=[str(snapshot)],
    )
    if package_spec is None or package_spec.loader is None:
        raise BenchmarkError("run-local execution snapshot cannot be loaded")
    package = importlib.util.module_from_spec(package_spec)
    sys.modules[package_name] = package
    package_spec.loader.exec_module(package)
    return importlib.import_module(f"{package_name}.execution")


def execute_run(config, paths, run_id, **kwargs):
    run_root, spec, _state = load_run(paths, run_id)
    verify_run_inputs(paths, run_root, spec)
    module = _snapshot_execution_module(run_root, spec)
    try:
        return module.execute_run(config, paths, run_id, **kwargs)
    except Exception as exc:
        if exc.__class__.__name__ == "BenchmarkError":
            raise BenchmarkError(str(exc)) from exc
        raise


del _module, _module_name, _name, _names, _contracts
