"""Storage services for benchmark automation."""
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

def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def object_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def atomic_write_json(path: Path, value: object) -> None:
    """Atomically replace a derived JSON index or mutable state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def write_new_json(path: Path, value: object) -> None:
    """Create immutable JSON evidence and refuse accidental replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(payload)

def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f'cannot read JSON {path}: {exc}') from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f'expected a JSON object in {path}')
    return value

def _baseline_identity(paths: Paths, baseline: Path, manifest: Mapping[str, Any], case_id: str) -> dict[str, str]:
    layout = 'baselines/<provider>/<baseline-id>'
    try:
        relative = baseline.resolve().relative_to((paths.root / 'baselines').resolve())
    except ValueError as exc:
        raise BenchmarkError(f'case {case_id!r} baseline must use {layout}') from exc
    if len(relative.parts) != 2:
        raise BenchmarkError(f'case {case_id!r} baseline must use {layout}')
    provider_id, baseline_id = relative.parts
    if BASELINE_NAME_PATTERN.fullmatch(provider_id) is None or BASELINE_NAME_PATTERN.fullmatch(baseline_id) is None:
        raise BenchmarkError(f'case {case_id!r} baseline must use {layout}')
    task_id = manifest.get('task_id')
    if not isinstance(task_id, str) or BASELINE_NAME_PATTERN.fullmatch(task_id) is None:
        raise BenchmarkError(f'case {case_id!r} baseline has an invalid task_id')
    expected = {'baseline_id': baseline_id, 'case_id': case_id, 'provider_id': provider_id}
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise BenchmarkError(f'case {case_id!r} baseline metadata {field} must be {value!r}')
    return {'provider_id': provider_id, 'task_id': task_id}

def resolve_inside(root: Path, value: str | Path, *, label: str) -> Path:
    root = root.resolve()
    candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise BenchmarkError(f'{label} escapes benchmark root: {value}') from exc
    return candidate

def resolve_runs_dir(benchmark_root: Path, configured_value: str | Path, *, override: str | Path | None=None, invocation_cwd: Path | None=None) -> Path:
    """Resolve mutable run output without weakening immutable-input containment."""
    if override is None:
        base = benchmark_root.resolve()
        value = Path(configured_value)
    else:
        base = (invocation_cwd or Path.cwd()).resolve()
        value = Path(override)
    value = value.expanduser()
    return value.resolve() if value.is_absolute() else (base / value).resolve()

def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True

def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)

def _existing_disk_root(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise BenchmarkError(f'cannot find an existing parent for runs_dir: {path}')
        candidate = parent
    return candidate

def _declared_files(workspace: Path, include_paths: Sequence[str]) -> list[Path]:
    workspace = workspace.resolve()
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in include_paths:
        target = resolve_inside(workspace, raw, label='declared input')
        if not target.exists():
            raise BenchmarkError(f'declared input does not exist: {target}')
        candidates = [target] if target.is_file() else sorted((path for path in target.rglob('*') if path.is_file() and '__pycache__' not in path.parts and (path.suffix.lower() not in {'.pyc', '.pyo'})), key=lambda path: path.as_posix().casefold())
        for path in candidates:
            resolved = path.resolve()
            try:
                resolved.relative_to(workspace)
            except ValueError as exc:
                raise BenchmarkError(f'declared input resolves outside workspace: {path}') from exc
            if resolved not in seen:
                seen.add(resolved)
                files.append(resolved)
    return sorted(files, key=lambda path: path.as_posix().casefold())

def task_manifest(workspace: Path, include_paths: Sequence[str]) -> list[dict[str, str]]:
    workspace = workspace.resolve()
    return [{'path': path.relative_to(workspace).as_posix(), 'sha256': file_sha256(path)} for path in _declared_files(workspace, include_paths)]

def task_fingerprint(workspace: Path, include_paths: Sequence[str]) -> str:
    """Match the frozen-baseline path-tab-file-hash manifest algorithm."""
    lines = [f"{entry['path']}\t{entry['sha256']}" for entry in task_manifest(workspace, include_paths)]
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()

def directory_manifest(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    if not root.is_dir():
        raise BenchmarkError(f'directory does not exist: {root}')
    files = sorted((path.resolve() for path in root.rglob('*') if path.is_file()), key=lambda path: path.as_posix().casefold())
    return [{'path': path.relative_to(root).as_posix(), 'sha256': file_sha256(path)} for path in files]

def directory_fingerprint(root: Path) -> str:
    manifest = directory_manifest(root)
    lines = [f"{item['path']}\t{item['sha256']}" for item in manifest]
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()

def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open('rb') as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BenchmarkError(f'cannot load benchmark config {path}: {exc}') from exc
    if not isinstance(value, dict):
        raise BenchmarkError('benchmark config root must be a table')
    return value

def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, 'tolist'):
        return _json_safe(value.tolist())
    if hasattr(value, 'item'):
        with contextlib.suppress(Exception):
            return _json_safe(value.item())
    return str(value)

def _new_sequence_dir(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000000):
        candidate = parent / f'{prefix}-{number:04d}'
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise BenchmarkError(f'could not allocate a new {prefix} evidence directory')

def _write_new_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


baseline_identity = _baseline_identity
is_within = _is_within
paths_overlap = _paths_overlap
existing_disk_root = _existing_disk_root
load_toml = _load_toml
json_safe = _json_safe
new_sequence_dir = _new_sequence_dir
write_new_text = _write_new_text
