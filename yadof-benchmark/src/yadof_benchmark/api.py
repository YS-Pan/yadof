"""Public API for code-first yadof benchmark workspaces."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import uuid
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
from .benchmark_runtime.execution import execute_existing_run
from .benchmark_runtime.planning import (
    load_workflow as _load_workflow,
    plan_workflow,
)
from .benchmark_runtime.results import inspect_run as _inspect_run
from .benchmark_runtime.storage import create_run, utc_now
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
    run_id: str | None = None,
    baselines_root: str | Path | None = None,
    event_sink: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    run_root = _prepare_workspace_run(
        workspace,
        run_id=run_id,
        baselines_root=baselines_root,
    )
    if event_sink is not None:
        event_sink(
            {
                "utc": utc_now(),
                "event": "run-created",
                "run": str(run_root),
                "log": str(run_root / "benchmark.log"),
            }
        )
    execute_existing_run(run_root, event_sink=event_sink)
    return _inspect_run(run_root)


def _prepare_workspace_run(
    workspace: str | Path | WorkflowRequest,
    *,
    run_id: str | None = None,
    baselines_root: str | Path | None = None,
) -> Path:
    """Create a planned run for the CLI's detached launcher."""

    spec = plan_workspace(workspace, baselines_root=baselines_root)
    return create_run(spec, run_id=run_id)


def _snapshot_runtime(run_root: Path):
    package_root = run_root / "driver" / "benchmark_runtime"
    init_path = package_root / "__init__.py"
    if not init_path.is_file():
        raise BenchmarkError(f"run driver snapshot is incomplete: {package_root}")
    package_name = f"_benchmark_driver_{uuid.uuid4().hex}"
    module_spec = importlib.util.spec_from_file_location(
        package_name,
        init_path,
        submodule_search_locations=[str(package_root)],
    )
    if module_spec is None or module_spec.loader is None:
        raise BenchmarkError(f"cannot load run driver: {package_root}")
    package = importlib.util.module_from_spec(module_spec)
    sys.modules[package_name] = package
    module_spec.loader.exec_module(package)
    return (
        importlib.import_module(f"{package_name}.execution"),
        importlib.import_module(f"{package_name}.results"),
    )


def resume_run(
    run: str | Path,
    *,
    event_sink: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    run_root = Path(run).resolve()
    execution, results = _snapshot_runtime(run_root)
    try:
        execution.execute_existing_run(run_root, event_sink=event_sink)
    except Exception as exc:
        if exc.__class__.__name__ == "BenchmarkError":
            raise BenchmarkError(str(exc)) from exc
        raise
    return results.inspect_run(run_root)


def inspect_run(run: str | Path) -> dict[str, Any]:
    return _inspect_run(run)


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
    "inspect_run",
    "load_workflow",
    "plan_workspace",
    "resume_run",
    "run_workspace",
    "user_doc_root",
]
