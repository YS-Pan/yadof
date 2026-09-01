"""Benchmark workspace creation and identity checks."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from .contracts import BenchmarkError, WORKSPACE_FORMAT
from .presets import PRESET_PROVENANCE_FORMAT, materialize_preset

_TIMESTAMP_PREFIX = re.compile(r"\d{8}_\d{6}(?:[-_]|$)")


def _timestamped_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    if not normalized:
        raise BenchmarkError(f"cannot derive a workspace name from {value!r}")
    if _TIMESTAMP_PREFIX.match(normalized):
        return normalized
    return f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}-{normalized}"

_DIRECTORIES = (
    "resources",
    "cells",
    "postprocessing",
    "visualizations",
    "reports",
    "temp",
)
def _write_new(path: Path, text: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise BenchmarkError(f"workspace output already exists: {path}") from exc


def init_workspace(
    path: str | Path,
    *,
    presets_root: str | Path,
    preset: str = "portable",
) -> dict[str, Any]:
    requested = Path(path).resolve()
    root = requested.with_name(_timestamped_name(requested.name))
    if root.exists() and any(root.iterdir()):
        raise BenchmarkError(f"workspace directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for name in _DIRECTORIES:
        (root / name).mkdir()
    marker_root = root / ".benchmark"
    marker_root.mkdir()
    public_preset, provenance = materialize_preset(presets_root, preset, root)
    marker = {
        "format": WORKSPACE_FORMAT,
        "workflow": "benchmark.py",
        "resources": "resources",
        "preset": public_preset["id"],
    }
    _write_new(
        marker_root / "workspace.json",
        json.dumps(marker, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    _write_new(
        marker_root / "preset.json",
        json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    return {
        "format": WORKSPACE_FORMAT,
        "workspace": str(root),
        "preset": public_preset,
        "provenance": str(marker_root / "preset.json"),
    }


def load_workspace(path: str | Path) -> Path:
    root = Path(path).resolve()
    marker_path = root / ".benchmark" / "workspace.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"not a benchmark workspace: {root}: {exc}") from exc
    if not isinstance(marker, dict) or marker.get("format") != WORKSPACE_FORMAT:
        raise BenchmarkError(f"invalid benchmark workspace marker: {marker_path}")
    if marker.get("workflow") != "benchmark.py" or marker.get("resources") != "resources":
        raise BenchmarkError(f"unsupported benchmark workspace layout: {marker_path}")
    if not (root / "benchmark.py").is_file():
        raise BenchmarkError(f"benchmark workflow does not exist: {root / 'benchmark.py'}")
    if not (root / "resources").is_dir():
        raise BenchmarkError(f"benchmark resources directory does not exist: {root / 'resources'}")
    return root


def load_workspace_preset(path: str | Path) -> dict[str, Any]:
    """Read preset provenance while preserving legacy workspace readability."""

    root = load_workspace(path)
    selected = root / ".benchmark" / "preset.json"
    if not selected.is_file():
        return {
            "format": PRESET_PROVENANCE_FORMAT,
            "id": "legacy",
            "source": "legacy-unrecorded",
            "catalog": None,
            "files": [],
        }
    try:
        value = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(
            f"cannot read benchmark preset provenance: {selected}: {exc}"
        ) from exc
    if not isinstance(value, dict) or value.get("format") != PRESET_PROVENANCE_FORMAT:
        raise BenchmarkError(f"unsupported benchmark preset provenance: {selected}")
    return value


__all__ = ["init_workspace", "load_workspace", "load_workspace_preset"]
