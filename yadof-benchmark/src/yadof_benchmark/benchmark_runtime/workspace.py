"""Benchmark workspace creation and identity checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import BenchmarkError, WORKSPACE_FORMAT

_DIRECTORIES = ("resources", "runs", "visualizations", "reports", "temp")
_TEMPLATE = '''"""Describe this benchmark's complete workflow."""
from yadof_benchmark import Benchmark


def build_benchmark(benchmark: Benchmark) -> None:
    """Register strategies, comparisons, and optional postprocessors."""
    # Add complete optimization.py implementations below, then compare them.
    # benchmark.strategy("reference", "resources/reference/optimization.py")
    # benchmark.compare(
    #     "main",
    #     baselines=["provider/task"],
    #     strategies=["reference"],
    #     seeds=[1],
    #     population=12,
    #     generations=20,
    # )
    pass
'''


def _write_new(path: Path, text: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise BenchmarkError(f"workspace output already exists: {path}") from exc


def init_workspace(path: str | Path) -> dict[str, Any]:
    root = Path(path).resolve()
    if root.exists() and any(root.iterdir()):
        raise BenchmarkError(f"workspace directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for name in _DIRECTORIES:
        (root / name).mkdir()
    marker_root = root / ".benchmark"
    marker_root.mkdir()
    _write_new(root / "benchmark.py", _TEMPLATE)
    marker = {
        "format": WORKSPACE_FORMAT,
        "workflow": "benchmark.py",
        "resources": "resources",
    }
    _write_new(
        marker_root / "workspace.json",
        json.dumps(marker, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    return {"format": WORKSPACE_FORMAT, "workspace": str(root)}


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


__all__ = ["init_workspace", "load_workspace"]
