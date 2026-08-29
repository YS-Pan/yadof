"""The small code-first builder used by workspace ``benchmark.py`` files."""
from __future__ import annotations

import inspect
import math
import re
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .contracts import (
    BenchmarkError,
    ComparisonSpec,
    EVIDENCE_CLASSES,
    PERFORMANCE_MIN_GENERATIONS,
    PERFORMANCE_MIN_PLANNED_EVALUATIONS,
    PERFORMANCE_MIN_POPULATION,
    PostprocessorSpec,
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
        self._representative_generation_seconds: float | None = None
        self._runs_dir = self.workspace / "runs"
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
        representative_generation_seconds: float | None = None,
        runs_dir: str | Path | None = None,
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
        if runs_dir is not None:
            self._runs_dir = self._path(runs_dir)
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
        self._strategies.append(
            StrategySpec(
                id=selected_id,
                name=selected_name,
                source=None if source is None else self._path(source),
                sources=MappingProxyType(mapped),
            )
        )
        return self

    def compare(
        self,
        comparison_id: str,
        *,
        baselines: Sequence[str],
        strategies: Sequence[str],
        seeds: Sequence[int],
        population: int,
        generations: int,
        reference: str | None = None,
    ) -> "Benchmark":
        selected_strategies = _items(strategies, label="comparison strategies")
        selected_seeds = tuple(seeds)
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
                population=_positive(population, label="population"),
                generations=_positive(generations, label="generations"),
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
        if self._evidence == "performance":
            for comparison in self._comparisons:
                if (
                    comparison.population < PERFORMANCE_MIN_POPULATION
                    or comparison.generations < PERFORMANCE_MIN_GENERATIONS
                ):
                    raise BenchmarkError(
                        f"performance comparison {comparison.id!r} has "
                        f"population={comparison.population}, "
                        f"generations={comparison.generations}; every performance "
                        "cell requires population >= "
                        f"{PERFORMANCE_MIN_POPULATION}, generations >= "
                        f"{PERFORMANCE_MIN_GENERATIONS}, and at least "
                        f"{PERFORMANCE_MIN_PLANNED_EVALUATIONS} planned real "
                        "evaluations. Use evidence='structural' for smaller "
                        "smoke or canary budgets."
                    )
        known = set(strategy_ids)
        for comparison in self._comparisons:
            missing = sorted(set(comparison.strategy_ids) - known)
            if missing:
                raise BenchmarkError(
                    f"comparison {comparison.id!r} uses unknown strategies: "
                    f"{', '.join(missing)}"
                )
        if not self._python.is_file():
            raise BenchmarkError(f"python executable does not exist: {self._python}")
        return WorkflowRequest(
            name=_id(self._name, label="workflow name"),
            evidence=self._evidence,
            strategies=tuple(self._strategies),
            comparisons=tuple(self._comparisons),
            postprocessors=tuple(self._postprocessors),
            fail_fast=(
                self._evidence == "structural"
                if self._fail_fast is None
                else self._fail_fast
            ),
            representative_generation_seconds=(
                self._representative_generation_seconds
            ),
            runs_dir=self._runs_dir,
            python=self._python,
            workspace=self.workspace,
            source=source.resolve(),
        )


__all__ = ["Benchmark"]
