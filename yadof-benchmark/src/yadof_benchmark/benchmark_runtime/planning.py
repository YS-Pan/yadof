"""Python workflow loading and deterministic run planning."""
from __future__ import annotations

import ast
import importlib.util
import sys
import uuid
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import (
    BaselineManifest,
    BenchmarkError,
    CellSpec,
    RunSpec,
    WorkflowRequest,
    freeze_json,
    replication_scope,
)
from .storage import (
    directory_digest,
    file_digest,
    object_digest,
)
from .workflow import Benchmark
from .workspace import load_workspace


_PROGRAM_DECLARATION = "YADOF_OPTIMIZATION_PROGRAM"
_PROGRAM_API = "yadof.optimize.program/v1"


def _declaration_node(tree: ast.Module) -> ast.AST | None:
    values: list[ast.AST] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == _PROGRAM_DECLARATION
            for target in statement.targets
        ):
            values.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == _PROGRAM_DECLARATION
            and statement.value is not None
        ):
            values.append(statement.value)
    if len(values) > 1:
        raise BenchmarkError(f"{_PROGRAM_DECLARATION} must be assigned exactly once")
    return None if not values else values[0]


def _helper_names(value: object, *, strategy_id: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise BenchmarkError(
            f"strategy {strategy_id!r} program helpers must be a literal tuple/list"
        )
    helpers: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise BenchmarkError(
                f"strategy {strategy_id!r} program helper paths must be strings"
            )
        path = PurePosixPath(item)
        if (
            not item
            or "\\" in item
            or path.is_absolute()
            or path.suffix != ".py"
            or any(part in {"", ".", ".."} for part in path.parts)
            or item == "optimization.py"
            or path.as_posix() != item
        ):
            raise BenchmarkError(
                f"strategy {strategy_id!r} program helper must be a canonical "
                f"relative .py path: {item!r}"
            )
        key = item.casefold()
        if key in seen:
            raise BenchmarkError(
                f"strategy {strategy_id!r} program helper path is duplicated: {item!r}"
            )
        seen.add(key)
        helpers.append(item)
    return tuple(helpers)


def _resolve_helper(source_root: Path, relative: str, *, strategy_id: str) -> Path:
    current = source_root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise BenchmarkError(
                f"strategy {strategy_id!r} program helper cannot use a symlink: "
                f"{relative!r}"
            )
    try:
        helper = current.resolve(strict=True)
    except OSError as exc:
        raise BenchmarkError(
            f"strategy {strategy_id!r} program helper does not exist: {relative!r}"
        ) from exc
    if not helper.is_relative_to(source_root) or not helper.is_file():
        raise BenchmarkError(
            f"strategy {strategy_id!r} program helper escapes its strategy directory "
            f"or is not a file: {relative!r}"
        )
    return helper


def _validate_strategy_source(
    path: Path, *, strategy_id: str
) -> Mapping[str, Path]:
    if not path.is_file():
        raise BenchmarkError(
            f"strategy {strategy_id!r} source does not exist: {path}"
        )
    if path.is_symlink():
        raise BenchmarkError(f"strategy {strategy_id!r} source cannot be a symlink: {path}")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise BenchmarkError(f"strategy {strategy_id!r} is not valid Python: {exc}") from exc
    declaration = _declaration_node(tree)
    if declaration is None:
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_optimization"
            for node in tree.body
        ):
            return MappingProxyType({"optimization.py": path.resolve()})
        raise BenchmarkError(
            f"strategy {strategy_id!r} must define build_optimization() or literal "
            f"{_PROGRAM_DECLARATION}"
        )
    try:
        raw = ast.literal_eval(declaration)
    except (TypeError, ValueError) as exc:
        raise BenchmarkError(
            f"strategy {strategy_id!r} {_PROGRAM_DECLARATION} must be literal"
        ) from exc
    if not isinstance(raw, dict):
        raise BenchmarkError(
            f"strategy {strategy_id!r} {_PROGRAM_DECLARATION} must be a literal mapping"
        )
    if raw.get("api") != _PROGRAM_API:
        raise BenchmarkError(
            f"strategy {strategy_id!r} program api must be {_PROGRAM_API!r}"
        )
    helpers = _helper_names(raw.get("helpers"), strategy_id=strategy_id)
    source_root = path.resolve().parent
    files: dict[str, Path] = {"optimization.py": path.resolve()}
    for helper in helpers:
        files[helper] = _resolve_helper(
            source_root, helper, strategy_id=strategy_id
        )
    return MappingProxyType(files)


def _strategy_digest(files: Mapping[str, Path]) -> str:
    return object_digest(
        [
            {"path": relative, "sha256": file_digest(source)}
            for relative, source in files.items()
        ]
    )


def _load_module(source: Path, workspace: Path) -> Any:
    module_name = f"_yadof_benchmark_workflow_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise BenchmarkError(f"cannot load benchmark workflow: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    sys.path.insert(0, str(workspace))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise BenchmarkError(f"benchmark.py import failed: {exc}") from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
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
    excludes = tuple(f"workspace/{item}" for item in manifest.materialize_excludes)
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
    for comparison in request.comparisons:
        if comparison.population is None or comparison.generations is None:
            raise BenchmarkError(f"comparison {comparison.id!r} budget is unresolved")
        for baseline_id in comparison.baseline_ids:
            baseline = baseline_by_id[baseline_id]
            for strategy_id in comparison.strategy_ids:
                strategy = strategy_by_id[strategy_id]
                source = strategy.source_for(baseline.id)
                strategy_files = _validate_strategy_source(
                    source, strategy_id=strategy.id
                )
                strategy_digest = _strategy_digest(strategy_files)
                for seed in comparison.seeds:
                    cell_id = f"c{len(cells) + 1:04d}"
                    cells.append(
                        CellSpec(
                            id=cell_id,
                            comparison_id=comparison.id,
                            baseline_id=baseline.id,
                            strategy_id=strategy.id,
                            seed=seed,
                            population=comparison.population,
                            generations=comparison.generations,
                            evidence=request.evidence,
                            replication_scope=replication_scope(
                                request.evidence, len(comparison.seeds)
                            ),
                            contains_slow_surrogate=(
                                comparison.contains_slow_surrogate
                            ),
                            representative_generation_seconds=(
                                request.representative_generation_seconds
                            ),
                            baseline_digest=baseline_digests[baseline.id],
                            strategy_digest=strategy_digest,
                            strategy_source=source,
                            strategy_files=strategy_files,
                            execution=freeze_json(baseline.execution),
                            contract=freeze_json(baseline.contract),
                        )
                    )
    return RunSpec(
        workflow=request,
        baselines=selected,
        cells=tuple(cells),
    )


__all__ = ["load_workflow", "plan_workflow"]
