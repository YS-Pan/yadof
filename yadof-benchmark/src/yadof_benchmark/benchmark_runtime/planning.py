"""Python workflow loading and deterministic run planning."""
from __future__ import annotations

import ast
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    BaselineManifest,
    BenchmarkError,
    CellSpec,
    RunSpec,
    WorkflowRequest,
    freeze_json,
)
from .storage import (
    directory_digest,
    driver_digest,
    file_digest,
    object_digest,
    slug,
    workflow_digest,
)
from .workflow import Benchmark
from .workspace import load_workspace


def _validate_strategy_source(path: Path, *, strategy_id: str) -> None:
    if not path.is_file():
        raise BenchmarkError(
            f"strategy {strategy_id!r} source does not exist: {path}"
        )
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise BenchmarkError(f"strategy {strategy_id!r} is not valid Python: {exc}") from exc
    if not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "build_optimization"
        for node in tree.body
    ):
        raise BenchmarkError(
            f"strategy {strategy_id!r} must define build_optimization()"
        )


def _load_module(source: Path, workspace: Path) -> Any:
    module_name = f"_yadof_benchmark_workflow_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise BenchmarkError(f"cannot load benchmark workflow: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    sys.path.insert(0, str(workspace))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise BenchmarkError(f"benchmark.py import failed: {exc}") from exc
    finally:
        sys.path.remove(str(workspace))
        sys.modules.pop(module_name, None)
    return module


def load_workflow(workspace: str | Path) -> WorkflowRequest:
    root = load_workspace(workspace)
    source = root / "benchmark.py"
    module = _load_module(source, root)
    build = getattr(module, "build_benchmark", None)
    if not callable(build):
        raise BenchmarkError("benchmark.py must define build_benchmark(benchmark)")
    builder = Benchmark(root)
    try:
        result = build(builder)
    except BenchmarkError:
        raise
    except Exception as exc:
        raise BenchmarkError(f"build_benchmark() failed: {exc}") from exc
    if result is not None:
        raise BenchmarkError("build_benchmark() must return None")
    request = builder.freeze(source)
    for postprocessor in request.postprocessors:
        callback = getattr(module, postprocessor.callback, None)
        if not callable(callback):
            raise BenchmarkError(
                f"postprocessor {postprocessor.id!r} callback is not available: "
                f"{postprocessor.callback}"
            )
    for strategy in request.strategies:
        selected = set(strategy.sources.values())
        if strategy.source is not None:
            selected.add(strategy.source)
        for path in selected:
            _validate_strategy_source(path, strategy_id=strategy.id)
    return request


def _baseline_digest(manifest: BaselineManifest) -> str:
    excludes = tuple(f"workspace/{item}" for item in manifest.snapshot_excludes)
    return directory_digest(manifest.root, excludes=excludes)


def plan_workflow(
    request: WorkflowRequest,
    baselines: Mapping[str, BaselineManifest],
) -> RunSpec:
    requested_baselines = {
        baseline_id
        for comparison in request.comparisons
        for baseline_id in comparison.baseline_ids
    }
    missing = sorted(requested_baselines - set(baselines))
    if missing:
        raise BenchmarkError(f"unknown baselines: {', '.join(missing)}")
    selected = tuple(baselines[item] for item in sorted(requested_baselines))
    baseline_digests = {item.id: _baseline_digest(item) for item in selected}
    baseline_by_id = {item.id: item for item in selected}
    strategy_by_id = {item.id: item for item in request.strategies}
    cells: list[CellSpec] = []
    cell_ids: set[str] = set()
    for comparison in request.comparisons:
        comparison_slug = slug(comparison.id)
        for baseline_id in comparison.baseline_ids:
            baseline = baseline_by_id[baseline_id]
            baseline_slug = slug(baseline.id)
            for strategy_id in comparison.strategy_ids:
                strategy = strategy_by_id[strategy_id]
                source = strategy.source_for(baseline.id)
                _validate_strategy_source(source, strategy_id=strategy.id)
                strategy_slug = slug(strategy.id)
                strategy_digest = file_digest(source)
                for seed in comparison.seeds:
                    cell_id = (
                        f"{comparison_slug}__{baseline_slug}__"
                        f"{strategy_slug}__seed-{seed}"
                    )
                    if cell_id in cell_ids:
                        raise BenchmarkError(f"cell path collision: {cell_id}")
                    cell_ids.add(cell_id)
                    cells.append(
                        CellSpec(
                            id=cell_id,
                            comparison_id=comparison.id,
                            baseline_id=baseline.id,
                            strategy_id=strategy.id,
                            seed=seed,
                            population=comparison.population,
                            generations=comparison.generations,
                            baseline_snapshot=(
                                f"inputs/baselines/{baseline_slug}/workspace"
                            ),
                            strategy_snapshot=(
                                "inputs/strategies/"
                                f"{strategy_slug}/{baseline_slug}/optimization.py"
                            ),
                            baseline_digest=baseline_digests[baseline.id],
                            strategy_digest=strategy_digest,
                            strategy_source=source,
                            execution=freeze_json(baseline.execution),
                            contract=freeze_json(baseline.contract),
                        )
                    )
    input_digest = workflow_digest(
        request.source, request.workspace / "resources"
    )
    provisional = RunSpec(
        workflow=request,
        baselines=selected,
        cells=tuple(cells),
        workflow_digest=input_digest,
        driver_digest=driver_digest(),
        digest="",
    )
    payload = provisional.to_dict()
    payload.pop("digest")
    return RunSpec(
        workflow=request,
        baselines=selected,
        cells=tuple(cells),
        workflow_digest=input_digest,
        driver_digest=provisional.driver_digest,
        digest=object_digest(payload),
    )


__all__ = ["load_workflow", "plan_workflow"]
