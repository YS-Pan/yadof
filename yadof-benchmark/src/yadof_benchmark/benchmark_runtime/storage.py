"""Persistence, provenance, and run-layout services."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from .baselines import snapshot_baseline
from .contracts import RUN_FORMAT, STATE_FORMAT, BenchmarkError, RunSpec

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_IGNORED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "jobs",
    "recorded_data",
    "visualization_outputs",
}
_CACHE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


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
    normalized_excludes = tuple(Path(item).as_posix().rstrip("/") for item in excludes)
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        parts = Path(relative).parts
        if any(part in _IGNORED_PARTS for part in parts):
            continue
        if len(parts) > 1 and parts[0] == ".yadof" and parts[1] != "workspace.json":
            continue
        if relative.endswith((".pyc", ".pyo")):
            continue
        if any(relative == item or relative.startswith(item + "/") for item in normalized_excludes):
            continue
        entries.append({"path": relative, "sha256": file_digest(path)})
    return object_digest(entries)


def workflow_digest(source: str | Path, resources: str | Path) -> str:
    source_path = Path(source).resolve()
    resource_root = Path(resources).resolve()
    entries = [{"path": "benchmark.py", "sha256": file_digest(source_path)}]
    for path in sorted(item for item in resource_root.rglob("*") if item.is_file()):
        relative = path.relative_to(resource_root).as_posix()
        if any(part in _CACHE_PARTS for part in Path(relative).parts):
            continue
        if relative.endswith((".pyc", ".pyo")):
            continue
        entries.append(
            {"path": f"resources/{relative}", "sha256": file_digest(path)}
        )
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
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise BenchmarkError(f"immutable output already exists: {target}") from exc


def write_new_json(path: str | Path, value: Any) -> None:
    write_new_text(path, _serialized(value))


def atomic_write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def atomic_write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(path, _serialized(value))


def safe_id(value: str, *, label: str) -> str:
    if not _ID_PATTERN.fullmatch(value):
        raise BenchmarkError(f"{label} must match {_ID_PATTERN.pattern!r}: {value!r}")
    return value


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if not normalized:
        raise BenchmarkError(f"cannot derive a path name from {value!r}")
    return normalized


def make_run_id(spec: RunSpec) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}-{slug(spec.workflow.name)}-{spec.digest[:12]}"


def driver_digest(root: str | Path | None = None) -> str:
    driver_root = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    names = ("__init__.py", "__main__.py", "_version.py", "api.py", "cli.py")
    paths = [driver_root / name for name in names]
    paths.extend(sorted((driver_root / "benchmark_runtime").glob("*.py")))
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise BenchmarkError(f"benchmark driver is incomplete: {', '.join(missing)}")
    entries = [
        {
            "path": path.relative_to(driver_root).as_posix(),
            "sha256": file_digest(path),
        }
        for path in paths
    ]
    return object_digest(entries)


def _copy_driver(destination: Path) -> None:
    package_root = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("__init__.py", "__main__.py", "_version.py", "api.py", "cli.py"):
        shutil.copy2(package_root / name, destination / name)
    shutil.copytree(
        package_root / "benchmark_runtime",
        destination / "benchmark_runtime",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _initial_state(run_id: str, spec: RunSpec) -> dict[str, Any]:
    now = utc_now()
    return {
        "format": STATE_FORMAT,
        "run_id": run_id,
        "status": "planned",
        "created_utc": now,
        "updated_utc": now,
        "cells": {
            cell.id: {"status": "planned", "attempts": [], "error": None}
            for cell in spec.cells
        },
        "postprocessors": {
            item.id: {"status": "planned", "attempts": [], "error": None}
            for item in spec.workflow.postprocessors
        },
    }


def _copy_workflow(spec: RunSpec, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(spec.workflow.source, destination / "benchmark.py")
    shutil.copytree(
        spec.workflow.workspace / "resources",
        destination / "resources",
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "*.pyc", "*.pyo"
        ),
    )
    if workflow_digest(destination / "benchmark.py", destination / "resources") != spec.workflow_digest:
        raise BenchmarkError("workflow changed after it was planned")


def create_run(spec: RunSpec, *, run_id: str | None = None) -> Path:
    selected_id = safe_id(run_id or make_run_id(spec), label="run id")
    runs_dir = spec.workflow.runs_dir.resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_root = runs_dir / selected_id
    if run_root.exists():
        raise BenchmarkError(f"run already exists: {run_root}")
    staging = runs_dir / f".{selected_id}.creating-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        _copy_driver(staging / "driver")
        if driver_digest(staging / "driver") != spec.driver_digest:
            raise BenchmarkError("driver changed after the workflow was planned")
        _copy_workflow(spec, staging / "inputs" / "workflow")
        manifests = {item.id: item for item in spec.baselines}
        copied_baselines: set[str] = set()
        copied_strategies: dict[str, str] = {}
        for cell in spec.cells:
            if cell.baseline_id not in copied_baselines:
                baseline_destination = staging / cell.baseline_snapshot
                snapshot_baseline(manifests[cell.baseline_id], baseline_destination.parent)
                copied_baselines.add(cell.baseline_id)
            strategy_destination = staging / cell.strategy_snapshot
            strategy_destination.parent.mkdir(parents=True, exist_ok=True)
            current = copied_strategies.get(cell.strategy_snapshot)
            if current is None:
                shutil.copy2(cell.strategy_source, strategy_destination)
                copied_strategies[cell.strategy_snapshot] = cell.strategy_digest
            elif current != cell.strategy_digest:
                raise BenchmarkError(
                    f"strategy snapshot collision at {cell.strategy_snapshot}"
                )
        for name in (
            "cells",
            "workspaces",
            "visualizations",
            "reports",
            "temp",
            "postprocessing",
        ):
            (staging / name).mkdir()
        spec_data = spec.to_dict()
        spec_data["created_utc"] = utc_now()
        write_new_json(staging / "spec.json", spec_data)
        write_new_json(staging / "state.json", _initial_state(selected_id, spec))
        os.replace(staging, run_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return run_root


def load_run(run_root: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(run_root).resolve()
    spec = read_json(root / "spec.json")
    state = read_json(root / "state.json")
    if spec.get("format") != RUN_FORMAT:
        raise BenchmarkError(f"not a benchmark run: {root}")
    if state.get("format") != STATE_FORMAT:
        raise BenchmarkError(f"invalid run state: {root / 'state.json'}")
    payload = dict(spec)
    expected = str(payload.pop("digest", ""))
    payload.pop("created_utc", None)
    if object_digest(payload) != expected:
        raise BenchmarkError(f"run specification digest mismatch: {root}")
    if state.get("run_id") != root.name:
        raise BenchmarkError(f"run state identity does not match directory {root.name!r}")
    return spec, state


def save_state(run_root: Path, state: dict[str, Any]) -> None:
    state["updated_utc"] = utc_now()
    atomic_write_json(run_root / "state.json", state)


def latest_attempt(run_root: Path, cell_state: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    attempts = cell_state.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise BenchmarkError("cell has no attempt")
    attempt = attempts[-1]
    if not isinstance(attempt, dict):
        raise BenchmarkError("cell attempt is invalid")
    return run_root / str(attempt["path"]), attempt


def prepare_attempt(
    run_root: Path,
    cell: Mapping[str, Any],
    state: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    cell_state = state["cells"][str(cell["id"])]
    number = len(cell_state["attempts"]) + 1
    attempt_root = run_root / "cells" / str(cell["id"]) / "attempts" / f"{number:04d}"
    attempt_root.mkdir(parents=True, exist_ok=False)
    workspace_token = hashlib.sha256(str(cell["id"]).encode("utf-8")).hexdigest()[:16]
    workspace = run_root / "workspaces" / workspace_token / f"{number:04d}"
    shutil.copytree(run_root / str(cell["baseline_snapshot"]), workspace)
    strategy_source = run_root / str(cell["strategy_snapshot"])
    strategy_destination = workspace / "submit" / "optimization.py"
    strategy_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(strategy_source, strategy_destination)
    attempt = {
        "number": number,
        "path": attempt_root.relative_to(run_root).as_posix(),
        "workspace": workspace.relative_to(run_root).as_posix(),
        "status": "planned",
        "created_utc": utc_now(),
        "finished_utc": None,
        "commands": [],
        "runtime_seconds": 0.0,
        "error": None,
    }
    cell_state["attempts"].append(attempt)
    cell_state["status"] = "planned"
    cell_state["error"] = None
    save_state(run_root, state)
    return attempt_root, workspace, attempt


def mark_interrupted(run_root: Path, state: dict[str, Any]) -> None:
    changed = False
    for cell_state in state["cells"].values():
        if cell_state.get("status") not in {"checked", "running"}:
            continue
        if cell_state.get("attempts"):
            attempt = cell_state["attempts"][-1]
            attempt["status"] = "interrupted"
            attempt["finished_utc"] = utc_now()
            attempt["error"] = "execution ended before a terminal command record"
        cell_state["status"] = "planned"
        cell_state["error"] = None
        changed = True
    for item in state.get("postprocessors", {}).values():
        if item.get("status") != "running":
            continue
        if item.get("attempts"):
            attempt = item["attempts"][-1]
            attempt["status"] = "interrupted"
            attempt["finished_utc"] = utc_now()
            attempt["error"] = "postprocessor ended without a terminal record"
        item["status"] = "planned"
        item["error"] = None
        changed = True
    if changed:
        save_state(run_root, state)


__all__ = [
    "atomic_write_json",
    "atomic_write_text",
    "canonical_json",
    "create_run",
    "directory_digest",
    "driver_digest",
    "file_digest",
    "json_safe",
    "latest_attempt",
    "load_run",
    "make_run_id",
    "mark_interrupted",
    "object_digest",
    "prepare_attempt",
    "read_json",
    "safe_id",
    "save_state",
    "slug",
    "utc_now",
    "workflow_digest",
    "write_new_json",
    "write_new_text",
]
