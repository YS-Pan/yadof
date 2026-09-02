"""Persistence and cell materialization for one benchmark workspace."""
from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import sys
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .._version import __version__ as benchmark_version
from .baselines import load_baseline, materialize_baseline
from .concurrency import resolve_simulation_concurrency
from .contracts import (
    SPEC_FORMAT,
    STATE_FORMAT,
    BenchmarkError,
    BenchmarkStorageError,
    RunSpec,
)

_IGNORED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "jobs",
    "recorded_data",
    "visualization_outputs",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def object_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_digest(root: str | Path, *, excludes: tuple[str, ...] = ()) -> str:
    directory = Path(root).resolve()
    entries: list[dict[str, str]] = []
    normalized_excludes = tuple(
        Path(item).as_posix().rstrip("/") for item in excludes
    )
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        parts = Path(relative).parts
        if any(part in _IGNORED_PARTS for part in parts):
            continue
        if ".yadof" in parts:
            marker = parts.index(".yadof")
            if marker + 1 < len(parts) and parts[marker + 1] != "workspace.json":
                continue
        if relative.endswith((".pyc", ".pyo")):
            continue
        if any(
            relative == item or relative.startswith(item + "/")
            for item in normalized_excludes
        ):
            continue
        entries.append({"path": relative, "sha256": file_digest(path)})
    return object_digest(entries)


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read JSON {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f"JSON root must be an object: {source}")
    return value


def _serialized(value: Any, *, indent: int | None = 2) -> str:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=indent,
    ) + "\n"


def write_new_text(path: str | Path, text: str) -> None:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise BenchmarkError(f"output already exists: {target}") from exc
    except OSError as exc:
        raise BenchmarkStorageError(f"cannot publish output {target}: {exc}") from exc


def write_new_json(path: str | Path, value: Any) -> None:
    write_new_text(path, _serialized(value))


def atomic_write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise BenchmarkStorageError(
            f"cannot atomically publish {target}: {exc}"
        ) from exc


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(path, _serialized(value))


def _package_version(distribution: str, module: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        try:
            imported = importlib.import_module(module)
        except Exception:
            return "unknown"
        return str(getattr(imported, "__version__", "unknown"))


def runtime_record() -> dict[str, Any]:
    """Record the installed runtime once, immediately before execution."""

    return {
        "format": "yadof.benchmark.runtime",
        "recorded_utc": utc_now(),
        "packages": {
            "yadof-benchmark": benchmark_version,
            "yadof": _package_version("yadof", "yadof"),
        },
        "python": {
            "version": platform.python_version(),
            "executable": str(Path(sys.executable).resolve()),
        },
        "host": {
            "node": platform.node(),
            "user": getpass.getuser(),
            "platform": platform.platform(),
        },
    }


def _initial_state(spec: RunSpec) -> dict[str, Any]:
    now = utc_now()
    return {
        "format": STATE_FORMAT,
        "status": "planned",
        "created_utc": now,
        "updated_utc": now,
        "started_utc": None,
        "finished_utc": None,
        "publication_failures": [],
        "cells": {
            cell.id: {
                "status": "planned",
                "display_label": cell.display_label,
                "baseline": cell.baseline_id,
                "strategy": cell.strategy_id,
                "seed": cell.seed,
                "path": f"cells/{cell.id}",
                "workspace": f"cells/{cell.id}/workspace",
                "created_utc": None,
                "finished_utc": None,
                "active_command": None,
                "commands": [],
                "runtime_seconds": 0.0,
                "simulation_concurrency": None,
                "result": None,
                "error": None,
            }
            for cell in spec.cells
        },
        "postprocessors": {
            item.id: {
                "status": "planned",
                "path": f"postprocessing/{item.id}",
                "created_utc": None,
                "finished_utc": None,
                "result": None,
                "error": None,
            }
            for item in spec.workflow.postprocessors
        },
    }


def initialize_workspace(spec: RunSpec) -> Path:
    """Create the direct execution records for a fresh benchmark workspace."""

    root = spec.workflow.workspace.resolve()
    for name in (
        "cells",
        "postprocessing",
        "visualizations",
        "reports",
        "temp",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    specification = spec.to_dict()
    specification["created_utc"] = utc_now()
    atomic_write_json(root / "runtime.json", runtime_record())
    atomic_write_json(root / "spec.json", specification)
    atomic_write_json(root / "state.json", _initial_state(spec))
    return root


def load_execution(workspace: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(workspace).resolve()
    spec = read_json(root / "spec.json")
    state = read_json(root / "state.json")
    runtime = read_json(root / "runtime.json")
    if spec.get("format") != SPEC_FORMAT:
        raise BenchmarkError(f"not a current benchmark workspace: {root}")
    if state.get("format") != STATE_FORMAT:
        raise BenchmarkError(f"invalid benchmark state: {root / 'state.json'}")
    if runtime.get("format") != "yadof.benchmark.runtime":
        raise BenchmarkError(f"invalid benchmark runtime record: {root / 'runtime.json'}")
    return spec, state


def save_state(workspace: Path, state: dict[str, Any]) -> None:
    state["updated_utc"] = utc_now()
    atomic_write_json(workspace / "state.json", state)


def _apply_simulation_concurrency(
    workspace: Path, execution: Mapping[str, Any]
) -> dict[str, Any] | None:
    value = execution.get("simulation_concurrency")
    if not isinstance(value, Mapping):
        return None
    mode = str(execution.get("mode", "")).strip().lower()
    prefix = {"fast": "FAST", "local": "LOCAL"}.get(mode)
    if prefix is None:
        raise BenchmarkError(
            f"simulation concurrency cannot be applied to execution mode {mode!r}"
        )
    resolved = resolve_simulation_concurrency(execution)
    if resolved is None:
        return None
    max_workers = int(resolved["resolved_max_workers"])
    config_path = workspace / "config.py"
    try:
        source = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BenchmarkError(
            f"cannot read materialized yadof config: {config_path}: {exc}"
        ) from exc
    if source and not source.endswith("\n"):
        source += "\n"
    source += (
        "\n# Applied by yadof-benchmark for this cell.\n"
        f"{prefix}_EVALUATION_MAX_WORKERS = {max_workers}\n"
    )
    atomic_write_text(config_path, source)
    return {
        "mode": mode,
        **resolved,
    }


def prepare_cell(
    root: Path,
    spec: Mapping[str, Any],
    cell: Mapping[str, Any],
    state: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    """Materialize one direct cell directory from the selected live inputs."""

    cell_id = str(cell["id"])
    cell_root = root / "cells" / cell_id
    baseline = spec["baselines"][str(cell["baseline"])]
    baseline_root = Path(str(baseline["source"])).resolve()
    manifest = load_baseline(baseline_root / "baseline.json")
    materialize_baseline(manifest, cell_root)
    workspace = cell_root / "workspace"

    declared_files = cell.get("strategy_files")
    if declared_files is None:
        declared_files = {"optimization.py": cell["strategy_source"]}
    if not isinstance(declared_files, Mapping) or "optimization.py" not in declared_files:
        raise BenchmarkError(
            f"cell {cell_id!r} strategy_files must map optimization.py and helpers"
        )
    submit_root = (workspace / "submit").resolve()
    for relative_value, source_value in declared_files.items():
        relative = str(relative_value)
        relative_path = PurePosixPath(relative)
        if (
            not relative
            or "\\" in relative
            or relative_path.is_absolute()
            or relative_path.suffix != ".py"
            or any(part in {"", ".", ".."} for part in relative_path.parts)
            or relative_path.as_posix() != relative
        ):
            raise BenchmarkError(
                f"cell {cell_id!r} has invalid strategy destination: {relative!r}"
            )
        source = Path(str(source_value))
        if source.is_symlink() or not source.is_file():
            raise BenchmarkError(
                f"cell {cell_id!r} strategy source is not a regular file: {source}"
            )
        destination = submit_root.joinpath(*relative_path.parts)
        resolved_parent = destination.parent.resolve()
        if not resolved_parent.is_relative_to(submit_root):
            raise BenchmarkError(
                f"cell {cell_id!r} strategy destination escapes submit/: {relative!r}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.resolve(), destination)
    simulation_concurrency = _apply_simulation_concurrency(
        workspace, cell.get("execution", {})
    )

    cell_state = state["cells"][cell_id]
    cell_state["created_utc"] = utc_now()
    cell_state["simulation_concurrency"] = simulation_concurrency
    cell_state["status"] = "planned"
    cell_state["error"] = None
    save_state(root, state)
    return cell_root, workspace, cell_state


__all__ = [
    "atomic_write_json",
    "atomic_write_text",
    "canonical_json",
    "directory_digest",
    "file_digest",
    "initialize_workspace",
    "json_safe",
    "load_execution",
    "object_digest",
    "prepare_cell",
    "read_json",
    "runtime_record",
    "save_state",
    "utc_now",
    "write_new_json",
    "write_new_text",
]
