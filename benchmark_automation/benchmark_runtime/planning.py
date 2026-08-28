"""Study parsing and deterministic run planning."""
from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import (
    STUDY_FORMAT,
    BaselineManifest,
    BenchmarkError,
    CellSpec,
    RunSpec,
    StrategySpec,
    StudyRequest,
    freeze_json,
)
from .storage import driver_digest, directory_digest, file_digest, object_digest, safe_id, slug

_ROOT_KEYS = {
    "format",
    "name",
    "baselines",
    "strategies",
    "seeds",
    "population",
    "generations",
    "reference",
    "fail_fast",
    "runs_dir",
    "python",
}


def _load_toml(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BenchmarkError(f"cannot read study {path}: {exc}") from exc
    return value


def _path(value: Any, *, root: Path, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkError(f"{label} must be a non-empty path string")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _string_list(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise BenchmarkError(f"{label} must be a non-empty list")
    items = tuple(str(item) for item in value)
    if any(not item for item in items) or len(set(items)) != len(items):
        raise BenchmarkError(f"{label} values must be non-empty and unique")
    return items


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BenchmarkError(f"{label} must be a positive integer")
    return value


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


def _strategy(data: Any, *, root: Path) -> StrategySpec:
    if not isinstance(data, Mapping):
        raise BenchmarkError("each strategies entry must be a table")
    unknown = sorted(set(data) - {"id", "name", "source", "sources"})
    if unknown:
        raise BenchmarkError(f"unknown strategy fields: {', '.join(unknown)}")
    strategy_id = safe_id(str(data.get("id", "")), label="strategy id")
    name = str(data.get("name", strategy_id)).strip()
    if not name:
        raise BenchmarkError(f"strategy {strategy_id!r} name is empty")
    source_value = data.get("source")
    source = None if source_value is None else _path(
        source_value, root=root, label=f"strategy {strategy_id!r} source"
    )
    sources_value = data.get("sources", {})
    if not isinstance(sources_value, Mapping):
        raise BenchmarkError(f"strategy {strategy_id!r} sources must be a table")
    sources: dict[str, Path] = {}
    for baseline_id, value in sources_value.items():
        sources[str(baseline_id)] = _path(
            value,
            root=root,
            label=f"strategy {strategy_id!r} source for {baseline_id!r}",
        )
    if source is None and not sources:
        raise BenchmarkError(f"strategy {strategy_id!r} has no source")
    for selected in {item for item in sources.values()} | ({source} if source else set()):
        _validate_strategy_source(selected, strategy_id=strategy_id)
    return StrategySpec(
        id=strategy_id,
        name=name,
        source=source,
        sources=MappingProxyType(sources),
    )


def load_study(
    path: str | Path,
    *,
    default_runs_dir: str | Path,
) -> StudyRequest:
    source = Path(path).resolve()
    data = _load_toml(source)
    unknown = sorted(set(data) - _ROOT_KEYS)
    if unknown:
        raise BenchmarkError(f"unknown study fields: {', '.join(unknown)}")
    if data.get("format") != STUDY_FORMAT:
        raise BenchmarkError(f"study must declare format = {STUDY_FORMAT!r}")
    name = safe_id(str(data.get("name", "")), label="study name")
    baseline_ids = _string_list(data.get("baselines"), label="baselines")
    seeds_value = data.get("seeds")
    if not isinstance(seeds_value, list) or not seeds_value:
        raise BenchmarkError("seeds must be a non-empty integer list")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in seeds_value):
        raise BenchmarkError("seeds must contain integers")
    seeds = tuple(int(item) for item in seeds_value)
    if len(set(seeds)) != len(seeds):
        raise BenchmarkError("seeds must be unique")
    strategies_value = data.get("strategies")
    if not isinstance(strategies_value, list) or not strategies_value:
        raise BenchmarkError("strategies must contain at least one table")
    strategies = tuple(_strategy(item, root=source.parent) for item in strategies_value)
    strategy_ids = [item.id for item in strategies]
    if len(set(strategy_ids)) != len(strategy_ids):
        raise BenchmarkError("strategy ids must be unique")
    reference_value = data.get("reference")
    reference = None if reference_value in (None, "") else str(reference_value)
    if reference is not None and reference not in strategy_ids:
        raise BenchmarkError(f"reference strategy is not declared: {reference!r}")
    fail_fast = data.get("fail_fast", False)
    if not isinstance(fail_fast, bool):
        raise BenchmarkError("fail_fast must be boolean")
    runs_value = data.get("runs_dir")
    runs_dir = (
        Path(default_runs_dir).resolve()
        if runs_value is None
        else _path(runs_value, root=source.parent, label="runs_dir")
    )
    python_value = data.get("python")
    python = (
        Path(sys.executable).resolve()
        if python_value is None
        else _path(python_value, root=source.parent, label="python")
    )
    if not python.is_file():
        raise BenchmarkError(f"python executable does not exist: {python}")
    return StudyRequest(
        name=name,
        baseline_ids=baseline_ids,
        strategies=strategies,
        seeds=seeds,
        population=_positive_int(data.get("population"), label="population"),
        generations=_positive_int(data.get("generations"), label="generations"),
        reference=reference,
        fail_fast=fail_fast,
        runs_dir=runs_dir,
        python=python,
        source=source,
    )


def _baseline_digest(manifest: BaselineManifest) -> str:
    excludes = tuple(f"workspace/{item}" for item in manifest.snapshot_excludes)
    return directory_digest(manifest.root, excludes=excludes)


def plan_study(
    request: StudyRequest,
    baselines: Mapping[str, BaselineManifest],
) -> RunSpec:
    missing = [item for item in request.baseline_ids if item not in baselines]
    if missing:
        raise BenchmarkError(f"unknown baselines: {', '.join(missing)}")
    selected = tuple(baselines[item] for item in request.baseline_ids)
    baseline_digests = {item.id: _baseline_digest(item) for item in selected}
    cells: list[CellSpec] = []
    cell_ids: set[str] = set()
    for baseline in selected:
        baseline_slug = slug(baseline.id)
        for strategy in request.strategies:
            source = strategy.source_for(baseline.id)
            digest = file_digest(source)
            strategy_slug = slug(strategy.id)
            for seed in request.seeds:
                cell_id = f"{baseline_slug}__{strategy_slug}__seed-{seed}"
                if cell_id in cell_ids:
                    raise BenchmarkError(f"cell path collision: {cell_id}")
                cell_ids.add(cell_id)
                cells.append(
                    CellSpec(
                        id=cell_id,
                        baseline_id=baseline.id,
                        strategy_id=strategy.id,
                        seed=seed,
                        population=request.population,
                        generations=request.generations,
                        baseline_snapshot=(
                            f"inputs/baselines/{baseline_slug}/workspace"
                        ),
                        strategy_snapshot=(
                            "inputs/strategies/"
                            f"{strategy_slug}/{baseline_slug}/optimization.py"
                        ),
                        baseline_digest=baseline_digests[baseline.id],
                        strategy_digest=digest,
                        strategy_source=source,
                        execution=freeze_json(baseline.execution),
                        contract=freeze_json(baseline.contract),
                    )
                )
    provisional = RunSpec(
        study=request,
        baselines=selected,
        cells=tuple(cells),
        driver_digest=driver_digest(),
        digest="",
    )
    payload = provisional.to_dict()
    payload.pop("digest")
    return RunSpec(
        study=request,
        baselines=selected,
        cells=tuple(cells),
        driver_digest=provisional.driver_digest,
        digest=object_digest(payload),
    )


__all__ = ["load_study", "plan_study"]
