"""The small code-first builder used by workspace ``benchmark.py`` files."""
from __future__ import annotations

import inspect
import math
import re
import sys
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .contracts import (
    BenchmarkError,
    BUDGET_PROFILES,
    ComparisonSpec,
    DEFAULT_GENERATIONS,
    DEFAULT_POPULATION,
    DEFAULT_SEEDS,
    EVIDENCE_CLASSES,
    PostprocessorSpec,
    SLOW_SURROGATE_GENERATIONS,
    StrategySpec,
    WorkflowRequest,
)

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _id(value: str, *, label: str) -> str:
    selected = str(value)
    if not _ID_PATTERN.fullmatch(selected):
        raise BenchmarkError(f"{label} must match {_ID_PATTERN.pattern!r}: {value!r}")
    return selected


def _items(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    selected = tuple(str(value) for value in values)
    if not selected or any(not value for value in selected):
        raise BenchmarkError(f"{label} must be non-empty")
    if len(set(selected)) != len(selected):
        raise BenchmarkError(f"{label} values must be unique")
    return selected


def _positive(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BenchmarkError(f"{label} must be a positive integer")
    return value


class Benchmark:
    """Mutable authoring facade that freezes into one workflow request."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        fallback = re.sub(r"[^A-Za-z0-9._-]+", "-", self.workspace.name).strip("-._")
        self._name = fallback or "benchmark"
        self._evidence: str | None = None
        self._fail_fast: bool | None = None
        self._cell_concurrency = 1
        self._representative_generation_seconds: float | None = None
        self._python = Path(sys.executable).resolve()
        self._strategies: list[StrategySpec] = []
        self._comparisons: list[ComparisonSpec] = []
        self._postprocessors: list[PostprocessorSpec] = []

    def _path(self, value: str | Path) -> Path:
        selected = Path(value)
        if not selected.is_absolute():
            selected = self.workspace / selected
        return selected.resolve()

    def configure(
        self,
        *,
        name: str | None = None,
        evidence: str | None = None,
        fail_fast: bool | None = None,
        cell_concurrency: int | None = None,
        representative_generation_seconds: float | None = None,
        python: str | Path | None = None,
    ) -> "Benchmark":
        if name is not None:
            self._name = _id(name, label="workflow name")
        if evidence is not None:
            selected_evidence = str(evidence)
            if selected_evidence not in EVIDENCE_CLASSES:
                raise BenchmarkError(
                    "evidence must be explicitly classified as "
                    f"{' or '.join(repr(item) for item in EVIDENCE_CLASSES)}"
                )
            self._evidence = selected_evidence
        if fail_fast is not None:
            if not isinstance(fail_fast, bool):
                raise BenchmarkError("fail_fast must be boolean")
            self._fail_fast = fail_fast
        if cell_concurrency is not None:
            self._cell_concurrency = _positive(
                cell_concurrency, label="cell_concurrency"
            )
        if representative_generation_seconds is not None:
            if (
                isinstance(representative_generation_seconds, bool)
                or not isinstance(representative_generation_seconds, (int, float))
                or not math.isfinite(float(representative_generation_seconds))
                or float(representative_generation_seconds) <= 0.0
            ):
                raise BenchmarkError(
                    "representative_generation_seconds must be a positive finite number"
                )
            self._representative_generation_seconds = float(
                representative_generation_seconds
            )
        if python is not None:
            self._python = self._path(python)
        return self

    def strategy(
        self,
        strategy_id: str,
        source: str | Path | None = None,
        *,
        name: str | None = None,
        sources: Mapping[str, str | Path] | None = None,
        slow_surrogate: bool = False,
    ) -> "Benchmark":
        selected_id = _id(strategy_id, label="strategy id")
        selected_name = str(name or selected_id).strip()
        if not selected_name:
            raise BenchmarkError(f"strategy {selected_id!r} name is empty")
        mapped = {
            str(baseline): self._path(path)
            for baseline, path in (sources or {}).items()
        }
        if source is None and not mapped:
            raise BenchmarkError(f"strategy {selected_id!r} has no source")
        if not isinstance(slow_surrogate, bool):
            raise BenchmarkError("slow_surrogate must be boolean")
        self._strategies.append(
            StrategySpec(
                id=selected_id,
                name=selected_name,
                source=None if source is None else self._path(source),
                sources=MappingProxyType(mapped),
                slow_surrogate=slow_surrogate,
            )
        )
        return self

    def compare(
        self,
        comparison_id: str,
        *,
        baselines: Sequence[str],
        strategies: Sequence[str],
        seeds: Sequence[int] | None = None,
        population: int | None = None,
        generations: int | None = None,
        reference: str | None = None,
    ) -> "Benchmark":
        selected_strategies = _items(strategies, label="comparison strategies")
        selected_seeds = tuple(DEFAULT_SEEDS if seeds is None else seeds)
        if not selected_seeds or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in selected_seeds
        ):
            raise BenchmarkError("comparison seeds must be non-empty integers")
        if len(set(selected_seeds)) != len(selected_seeds):
            raise BenchmarkError("comparison seeds must be unique")
        if reference is not None and reference not in selected_strategies:
            raise BenchmarkError(
                f"reference strategy is not selected by comparison: {reference!r}"
            )
        self._comparisons.append(
            ComparisonSpec(
                id=_id(comparison_id, label="comparison id"),
                baseline_ids=_items(baselines, label="comparison baselines"),
                strategy_ids=selected_strategies,
                seeds=selected_seeds,
                population=(
                    None if population is None else _positive(population, label="population")
                ),
                generations=(
                    None
                    if generations is None
                    else _positive(generations, label="generations")
                ),
                reference=reference,
            )
        )
        return self

    def postprocess(
        self,
        postprocessor_id: str,
        callback: Callable[[object], object],
    ) -> "Benchmark":
        if not inspect.isfunction(callback):
            raise BenchmarkError("postprocessor callback must be a top-level function")
        if callback.__name__ == "<lambda>" or callback.__qualname__ != callback.__name__:
            raise BenchmarkError("postprocessor callback must be a named top-level function")
        self._postprocessors.append(
            PostprocessorSpec(
                id=_id(postprocessor_id, label="postprocessor id"),
                callback=callback.__name__,
            )
        )
        return self

    def freeze(self, source: Path) -> WorkflowRequest:
        strategy_ids = [item.id for item in self._strategies]
        comparison_ids = [item.id for item in self._comparisons]
        postprocessor_ids = [item.id for item in self._postprocessors]
        for label, values in (
            ("strategy", strategy_ids),
            ("comparison", comparison_ids),
            ("postprocessor", postprocessor_ids),
        ):
            if len(set(values)) != len(values):
                raise BenchmarkError(f"{label} ids must be unique")
        if not self._strategies:
            raise BenchmarkError("benchmark.py must declare at least one strategy")
        if not self._comparisons:
            raise BenchmarkError("benchmark.py must declare at least one comparison")
        if self._evidence is None:
            raise BenchmarkError(
                "benchmark.configure(evidence=...) must explicitly classify this "
                "workflow as 'structural' or 'performance'"
            )
        known = set(strategy_ids)
        strategy_by_id = {item.id: item for item in self._strategies}
        resolved_comparisons: list[ComparisonSpec] = []
        for comparison in self._comparisons:
            missing = sorted(set(comparison.strategy_ids) - known)
            if missing:
                raise BenchmarkError(
                    f"comparison {comparison.id!r} uses unknown strategies: "
                    f"{', '.join(missing)}"
                )
            contains_slow_surrogate = any(
                strategy_by_id[item].slow_surrogate
                for item in comparison.strategy_ids
            )
            resolved_comparisons.append(
                replace(
                    comparison,
                    population=(
                        DEFAULT_POPULATION
                        if comparison.population is None
                        else comparison.population
                    ),
                    generations=(
                        SLOW_SURROGATE_GENERATIONS
                        if comparison.generations is None
                        and contains_slow_surrogate
                        else DEFAULT_GENERATIONS
                        if comparison.generations is None
                        else comparison.generations
                    ),
                    contains_slow_surrogate=contains_slow_surrogate,
                )
            )
        if not self._python.is_file():
            raise BenchmarkError(f"python executable does not exist: {self._python}")
        return WorkflowRequest(
            name=_id(self._name, label="workflow name"),
            evidence=self._evidence,
            strategies=tuple(self._strategies),
            comparisons=tuple(resolved_comparisons),
            postprocessors=tuple(self._postprocessors),
            fail_fast=(
                self._evidence == "structural"
                if self._fail_fast is None
                else self._fail_fast
            ),
            cell_concurrency=self._cell_concurrency,
            representative_generation_seconds=(
                self._representative_generation_seconds
            ),
            budget_profile="declared",
            preset=MappingProxyType({}),
            python=self._python,
            workspace=self.workspace,
            source=source.resolve(),
        )


def apply_budget_profile(
    request: WorkflowRequest,
    profile: str = "declared",
) -> WorkflowRequest:
    """Mechanically derive a bounded plan without changing its scientific inputs."""

    selected = str(profile)
    if selected not in BUDGET_PROFILES:
        raise BenchmarkError(
            f"budget profile must be one of {', '.join(BUDGET_PROFILES)}: {profile!r}"
        )
    comparisons = request.comparisons
    if selected == "smoke":
        comparisons = tuple(
            replace(comparison, generations=1)
            for comparison in request.comparisons
        )
    return replace(
        request,
        comparisons=comparisons,
        budget_profile=selected,
    )


__all__ = ["Benchmark", "apply_budget_profile"]
