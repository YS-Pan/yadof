"""Discovery and clean snapshot handling for self-describing baselines."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping

from .contracts import BASELINE_FORMAT, BaselineManifest, BenchmarkError, freeze_json

_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]*\Z")
_IGNORED_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "jobs",
    "recorded_data",
    "visualization_outputs",
}
_YADOF_RUNTIME_NAMES = {
    "campaign.lock",
    "fast_scratch",
    "logs",
    "optimization",
    "surrogate",
    "tool_output",
}
_MANIFEST_FIELDS = {
    "format", "id", "name", "description", "workspace", "execution",
    "contract", "estimates", "snapshot_excludes",
}


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read baseline manifest {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise BenchmarkError(f"baseline manifest must be an object: {path}")
    return value


def _inside(root: Path, candidate: Path, *, label: str) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise BenchmarkError(f"{label} escapes {root}: {candidate}") from exc
    return candidate


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BenchmarkError(f"{label} must be a positive integer")
    return value


def load_baseline(path: str | Path) -> BaselineManifest:
    manifest_path = Path(path).resolve()
    data = _read_json(manifest_path)
    unknown = sorted(set(data) - _MANIFEST_FIELDS)
    if unknown:
        raise BenchmarkError(f"unknown fields in {manifest_path}: {', '.join(unknown)}")
    if data.get("format") != BASELINE_FORMAT:
        raise BenchmarkError(
            f"{manifest_path} must declare format = {BASELINE_FORMAT!r}"
        )
    baseline_id = str(data.get("id", ""))
    if not _ID_PATTERN.fullmatch(baseline_id) or ".." in baseline_id.split("/"):
        raise BenchmarkError(f"invalid baseline id {baseline_id!r} in {manifest_path}")
    name = str(data.get("name", "")).strip()
    if not name:
        raise BenchmarkError(f"baseline {baseline_id!r} has no name")
    description = str(data.get("description", "")).strip()
    if not description:
        raise BenchmarkError(f"baseline {baseline_id!r} has no description")
    root = manifest_path.parent
    workspace_value = data.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value:
        raise BenchmarkError(f"baseline {baseline_id!r} has no workspace")
    workspace = _inside(root, root / workspace_value, label="baseline workspace")
    if not workspace.is_dir():
        raise BenchmarkError(f"baseline workspace does not exist: {workspace}")

    execution = data.get("execution")
    contract = data.get("contract")
    estimates = data.get("estimates", {})
    if not isinstance(execution, Mapping):
        raise BenchmarkError(f"baseline {baseline_id!r} execution must be an object")
    if not isinstance(contract, Mapping):
        raise BenchmarkError(f"baseline {baseline_id!r} contract must be an object")
    if not isinstance(estimates, Mapping):
        raise BenchmarkError(f"baseline {baseline_id!r} estimates must be an object")
    _positive_int(contract.get("objective_count"), label="contract.objective_count")
    shapes = contract.get("rawdata_shapes")
    if not isinstance(shapes, Mapping):
        raise BenchmarkError(f"baseline {baseline_id!r} has no rawdata_shapes object")
    for field, shape in shapes.items():
        if not isinstance(field, str) or not isinstance(shape, list):
            raise BenchmarkError(f"invalid rawdata shape entry in {baseline_id!r}")
        if any(isinstance(size, bool) or not isinstance(size, int) or size < 0 for size in shape):
            raise BenchmarkError(f"invalid rawdata shape for {field!r} in {baseline_id!r}")
    timeout = execution.get("timeout_seconds", 7200)
    _positive_int(timeout, label="execution.timeout_seconds")
    mode = execution.get("mode")
    if mode is not None and (not isinstance(mode, str) or not mode.strip()):
        raise BenchmarkError(f"baseline {baseline_id!r} execution.mode is invalid")

    excludes = data.get("snapshot_excludes", [])
    if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
        raise BenchmarkError(f"baseline {baseline_id!r} snapshot_excludes must be strings")
    normalized_excludes: list[str] = []
    for item in excludes:
        candidate = _inside(workspace, workspace / item, label="snapshot exclusion")
        relative = candidate.relative_to(workspace).as_posix()
        if relative in (".", ""):
            raise BenchmarkError("a snapshot exclusion cannot name the workspace root")
        fixed_inputs = {"config.py", "submit", "job_template", ".yadof/workspace.json"}
        if relative in fixed_inputs or relative.startswith(("submit/", "job_template/")):
            raise BenchmarkError(f"snapshot exclusion names behavioral input: {relative}")
        normalized_excludes.append(relative)

    return BaselineManifest(
        id=baseline_id,
        name=name,
        description=description,
        root=root,
        workspace=workspace,
        execution=freeze_json(execution),
        contract=freeze_json(contract),
        estimates=freeze_json(estimates),
        snapshot_excludes=tuple(sorted(set(normalized_excludes))),
    )


def discover_baselines(root: str | Path) -> dict[str, BaselineManifest]:
    baseline_root = Path(root).resolve()
    if not baseline_root.is_dir():
        raise BenchmarkError(f"baseline root does not exist: {baseline_root}")
    discovered: dict[str, BaselineManifest] = {}
    for manifest_path in sorted(baseline_root.rglob("baseline.json")):
        manifest = load_baseline(manifest_path)
        source_id = manifest_path.parent.relative_to(baseline_root).as_posix()
        if source_id != manifest.id:
            raise BenchmarkError(
                "baseline source directory must match its semantic id: "
                f"expected {baseline_root / Path(*manifest.id.split('/'))}, "
                f"found {manifest_path.parent}"
            )
        discovered[manifest.id] = manifest
    if not discovered:
        raise BenchmarkError(f"no baseline.json found below {baseline_root}")
    return discovered


def _ignore_for(manifest: BaselineManifest, source: str, names: list[str]) -> set[str]:
    source_path = Path(source).resolve()
    relative_root = source_path.relative_to(manifest.workspace).as_posix()
    ignored: set[str] = set()
    for name in names:
        if name in _IGNORED_NAMES or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
            continue
        relative = Path(relative_root, name).as_posix()
        if relative.startswith("./"):
            relative = relative[2:]
        if relative in manifest.snapshot_excludes:
            ignored.add(name)
    if source_path.name == ".yadof":
        ignored.update(name for name in names if name in _YADOF_RUNTIME_NAMES)
    return ignored


def snapshot_baseline(manifest: BaselineManifest, destination: Path) -> None:
    """Copy one manifest and its complete clean workspace."""

    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(manifest.root / "baseline.json", destination / "baseline.json")
    shutil.copytree(
        manifest.workspace,
        destination / "workspace",
        ignore=lambda source, names: _ignore_for(manifest, source, names),
    )


__all__ = ["discover_baselines", "load_baseline", "snapshot_baseline"]
