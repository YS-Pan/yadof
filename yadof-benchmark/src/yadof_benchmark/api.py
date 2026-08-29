"""Public API for code-first yadof benchmark workspaces."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .benchmark_runtime.baselines import discover_baselines as _discover_baselines
from .benchmark_runtime.contracts import (
    BaselineManifest,
    BenchmarkError,
    ComparisonSpec,
    PostprocessContext,
    RunSpec,
    WorkflowRequest,
)
from .benchmark_runtime.execution import execute_workspace
from .benchmark_runtime.planning import (
    load_workflow as _load_workflow,
    plan_workflow,
)
from .benchmark_runtime.results import inspect_workspace as _inspect_workspace
from .benchmark_runtime.storage import initialize_workspace, utc_now
from .benchmark_runtime.workflow import Benchmark
from .benchmark_runtime.workspace import init_workspace as _init_workspace

_PACKAGE_ROOT = Path(__file__).resolve().parent


def _resource_root(name: str) -> Path:
    source_tree = _PACKAGE_ROOT.parents[1] / name
    if source_tree.is_dir():
        return source_tree
    installed = _PACKAGE_ROOT / "_resources" / name
    if installed.is_dir():
        return installed
    raise BenchmarkError(f"installed benchmark resource is missing: {name}")


def user_doc_root() -> Path:
    """Return the version-matched installed user documentation root."""

    return _resource_root("user_doc")


def discover_baselines(
    root: str | Path | None = None,
) -> dict[str, BaselineManifest]:
    return _discover_baselines(root or _resource_root("baselines"))


def init_workspace(path: str | Path) -> dict[str, Any]:
    return _init_workspace(path)


def load_workflow(workspace: str | Path) -> WorkflowRequest:
    return _load_workflow(workspace)


def plan_workspace(
    workspace: str | Path | WorkflowRequest,
    *,
    baselines_root: str | Path | None = None,
) -> RunSpec:
    request = (
        _load_workflow(workspace)
        if isinstance(workspace, (str, Path))
        else workspace
    )
    return plan_workflow(request, discover_baselines(baselines_root))


def run_workspace(
    workspace: str | Path | WorkflowRequest,
    *,
    baselines_root: str | Path | None = None,
    event_sink: Callable[[Mapping[str, Any]], None] | None = None,
    stream_child_output: bool = False,
) -> dict[str, Any]:
    """Execute the workspace's one benchmark using the installed packages."""

    spec = plan_workspace(workspace, baselines_root=baselines_root)
    root = initialize_workspace(spec)
    if event_sink is not None:
        event_sink(
            {
                "utc": utc_now(),
                "event": "workspace-created",
                "workspace": str(root),
                "log": str(root / "benchmark.log"),
            }
        )
    execute_workspace(
        root,
        event_sink=event_sink,
        stream_child_output=stream_child_output,
    )
    return _inspect_workspace(root)


def inspect_workspace(workspace: str | Path) -> dict[str, Any]:
    return _inspect_workspace(workspace)


__all__ = [
    "BaselineManifest",
    "Benchmark",
    "BenchmarkError",
    "ComparisonSpec",
    "PostprocessContext",
    "RunSpec",
    "WorkflowRequest",
    "discover_baselines",
    "init_workspace",
    "inspect_workspace",
    "load_workflow",
    "plan_workspace",
    "run_workspace",
    "user_doc_root",
]
