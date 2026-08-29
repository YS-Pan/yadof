"""Benchmark workspace creation and identity checks."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from .contracts import BenchmarkError, WORKSPACE_FORMAT

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
_TEMPLATE = '''"""Describe this benchmark's complete workflow."""
from yadof_benchmark import Benchmark, PostprocessContext


def summarize_results(context: PostprocessContext) -> dict[str, str]:
    """Create optional workspace reports or visualizations after collection."""
    # Read context.results, then write durable artifacts below context.reports or
    # context.visualizations. Return a small JSON-compatible summary.
    return {}


def build_benchmark(benchmark: Benchmark) -> None:
    """Register this workflow's strategies, comparisons, and postprocessors."""
    # Keep the complete workflow discoverable here. Strategy IDs and names describe
    # their actual algorithm, not a temporary role such as "reference" or
    # "real-search". Each source is a complete submit/optimization.py module.
    # "structural" is for smoke/canary integration evidence only. It must not be
    # presented as algorithm performance evidence. Use "performance" only for a
    # deliberately authorized performance campaign after plan and bounded smoke.
    # Comparisons default to one seed, population=200, and generations=50. If any
    # selected strategy declares slow_surrogate=True, the default is 15 generations.
    # Pass explicit values when the benchmark needs a different budget or multiple
    # seeds. Single-seed performance evidence is reported as exploratory.
    # benchmark.configure(
    #     name="saw-algorithm-comparison",
    #     evidence="structural",
    #     # Cells enter a FIFO scheduler. Keep one cell active unless independent
    #     # simulator/license/memory capacity has been reviewed for this host.
    #     cell_concurrency=1,
    #     # Structural workflows default to fail-fast; performance workflows default
    #     # to continuing independent cells while retaining a nonzero final status.
    #     # Optional external reference for descriptive surrogate-training context.
    #     # Use an expensive representative generation, not this cheap cell runtime.
    #     representative_generation_seconds=7200.0,
    # )
    # benchmark.strategy(
    #     "nsga3",
    #     "resources/strategies/nsga3/optimization.py",
    #     name="NSGA-III",
    #     # Set True for strategies that repeatedly train a slow surrogate such as
    #     # a neural network. This changes only the default generation count.
    #     slow_surrogate=False,
    # )
    # benchmark.compare(
    #     "main",
    #     baselines=["ngspice/saw-ladder"],
    #     strategies=["nsga3"],
    #     # This intentionally small budget is structural-only.
    #     population=12,
    #     generations=3,
    # )
    # benchmark.postprocess("summary", summarize_results)
    pass
'''


def _write_new(path: Path, text: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise BenchmarkError(f"workspace output already exists: {path}") from exc


def init_workspace(path: str | Path) -> dict[str, Any]:
    requested = Path(path).resolve()
    root = requested.with_name(_timestamped_name(requested.name))
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
