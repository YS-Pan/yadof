"""Public API for the source-checkout benchmark."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from benchmark_runtime.baselines import discover_baselines as _discover_baselines
from benchmark_runtime.contracts import (
    BaselineManifest,
    BenchmarkError,
    RunSpec,
    StudyRequest,
)
from benchmark_runtime.execution import execute_existing_run
from benchmark_runtime.planning import (
    load_study as _load_study,
    plan_study as _plan_study,
)
from benchmark_runtime.results import inspect_run as _inspect_run
from benchmark_runtime.storage import create_run

_AUTOMATION_ROOT = Path(__file__).resolve().parent
_BASELINES_ROOT = _AUTOMATION_ROOT / "baselines"
_DEFAULT_RUNS_ROOT = _AUTOMATION_ROOT.parent / "temp"


def discover_baselines(
    root: str | Path | None = None,
) -> dict[str, BaselineManifest]:
    return _discover_baselines(root or _BASELINES_ROOT)


def load_study(path: str | Path) -> StudyRequest:
    return _load_study(path, default_runs_dir=_DEFAULT_RUNS_ROOT)


def plan_study(study: str | Path | StudyRequest) -> RunSpec:
    request = load_study(study) if isinstance(study, (str, Path)) else study
    return _plan_study(request, discover_baselines())


def run_study(
    study: str | Path | StudyRequest,
    *,
    run_id: str | None = None,
    event_sink: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    request = load_study(study) if isinstance(study, (str, Path)) else study
    spec = _plan_study(request, discover_baselines())
    run_root = create_run(spec, run_id=run_id)
    execute_existing_run(run_root, event_sink=event_sink)
    return _inspect_run(run_root)


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
    "BenchmarkError",
    "RunSpec",
    "StudyRequest",
    "discover_baselines",
    "inspect_run",
    "load_study",
    "plan_study",
    "resume_run",
    "run_study",
]
