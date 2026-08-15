"""Generation-scoped immutable task-source snapshots and fingerprints."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
import shutil
import tempfile
from typing import Mapping

from .config import LoadedConfig
from .job_template import api as job_template_api
from .workspace import WorkspaceContext


RECORDER_CONFIG_NAMES = frozenset(
    {
        "RECORDED_DATA_DIR",
        "HISTORY_SEGMENT_MAX_CANDIDATES",
        "HISTORY_SEGMENT_TARGET_BYTES",
        "HISTORY_MAX_CANDIDATE_BYTES",
        "HISTORY_UNPUBLISHED_MAX_CANDIDATES",
        "HISTORY_UNPUBLISHED_MAX_BYTES",
        "HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES",
        "HISTORY_WRITER_SHUTDOWN_TIMEOUT_SEC",
    }
)


@dataclass(frozen=True, slots=True)
class GenerationTaskSnapshot:
    """One coherent task/config definition used by a complete generation."""

    config: LoadedConfig
    source_directory: Path
    interpretation_fingerprint: str
    evaluation_fingerprint: str
    task_snapshot_id: str
    parameter_names: tuple[str, ...]
    objective_names: tuple[str, ...]
    source_hashes: Mapping[str, str]

    def close(self) -> None:
        shutil.rmtree(self.source_directory, ignore_errors=True)


def create_generation_snapshot(config: LoadedConfig) -> GenerationTaskSnapshot:
    """Capture task-source bytes before any candidate in a generation starts."""

    source_root = config.workspace.job_template_dir.resolve()
    snapshot_root = Path(tempfile.mkdtemp(prefix="yadof-task-snapshot-"))
    try:
        _copy_task_tree(source_root, snapshot_root)
        snapshot_workspace = replace(config.workspace, job_template_dir=snapshot_root)
        values = dict(config.values)
        values["JOB_TEMPLATE_DIR"] = snapshot_root
        snapshot_config = replace(
            config,
            workspace=snapshot_workspace,
            values=MappingProxyType(values),
        )
        hashes = _source_hashes(snapshot_root)
        interpretation_files = _dependency_files(
            snapshot_root, ("parameters_constraints.py", "calc_cost.py")
        )
        evaluation_files = _dependency_files(
            snapshot_root, ("workflow.py", "evaluation.py")
        )
        interpretation_fingerprint = _hash_mapping(
            {name: hashes[name] for name in sorted(interpretation_files) if name in hashes}
        )
        evaluation_payload: dict[str, object] = {
            "sources": {
                name: hashes[name]
                for name in sorted(evaluation_files)
                if name in hashes
            },
            "config": _semantic_config(config),
        }
        evaluation_fingerprint = _hash_json(evaluation_payload)
        task_snapshot_id = _hash_json(
            {
                "sources": dict(hashes),
                "config": _semantic_config(config),
            }
        )
        parameter_names = tuple(
            job_template_api.get_parameter_names(snapshot_workspace)
        )
        objective_names = tuple(
            job_template_api.get_objective_names(snapshot_workspace)
        )
        return GenerationTaskSnapshot(
            config=snapshot_config,
            source_directory=snapshot_root,
            interpretation_fingerprint=interpretation_fingerprint,
            evaluation_fingerprint=evaluation_fingerprint,
            task_snapshot_id=task_snapshot_id,
            parameter_names=parameter_names,
            objective_names=objective_names,
            source_hashes=MappingProxyType(hashes),
        )
    except Exception:
        shutil.rmtree(snapshot_root, ignore_errors=True)
        raise


def _copy_task_tree(source_root: Path, destination_root: Path) -> None:
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)
    for source in sorted(source_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative = source.relative_to(source_root)
        if any(part in {"__pycache__", ".pytest_cache", "rawData"} for part in relative.parts):
            continue
        if len(relative.parts) == 1 and source.name.lower().endswith(
            (".aedtresults", ".aedt.lock")
        ):
            continue
        destination = destination_root / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not source.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _source_hashes(root: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        output[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return output


def _dependency_files(root: Path, roots: tuple[str, ...]) -> set[str]:
    available = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*.py")
        if path.is_file()
    }
    pending = [name for name in roots if name in available]
    selected: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in selected:
            continue
        selected.add(relative)
        for imported in _local_imports(available[relative], root, available):
            if imported not in selected:
                pending.append(imported)
    return selected


def _local_imports(path: Path, root: Path, available: Mapping[str, Path]) -> set[str]:
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (SyntaxError, ValueError):
        return set()
    output: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.append(base)
            names.extend(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
        for name in names:
            parts = tuple(part for part in name.split(".") if part)
            for count in range(len(parts), 0, -1):
                module = "/".join(parts[:count]) + ".py"
                package = "/".join(parts[:count]) + "/__init__.py"
                if module in available:
                    output.add(module)
                    break
                if package in available:
                    output.add(package)
                    break
    return output


def _semantic_config(config: LoadedConfig) -> dict[str, object]:
    return {
        name: _json_value(value)
        for name, value in sorted(config.values.items())
        if name not in RECORDER_CONFIG_NAMES
    }


def _json_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _hash_mapping(value: Mapping[str, str]) -> str:
    return _hash_json(dict(value))


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "GenerationTaskSnapshot",
    "RECORDER_CONFIG_NAMES",
    "create_generation_snapshot",
]
