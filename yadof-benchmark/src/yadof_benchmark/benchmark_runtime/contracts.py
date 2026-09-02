"""Dependency-free contracts for code-first benchmark workspaces."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

BASELINE_FORMAT = "yadof.benchmark.baseline"
WORKSPACE_FORMAT = "yadof.benchmark.workspace"
WORKFLOW_FORMAT = "yadof.benchmark.workflow"
SPEC_FORMAT = "yadof.benchmark.spec"
STATE_FORMAT = "yadof.benchmark.state"
EVIDENCE_CLASSES = ("structural", "performance")
BUDGET_PROFILES = ("declared", "smoke")
DEFAULT_SEED = 101
DEFAULT_SEEDS = (DEFAULT_SEED,)
DEFAULT_POPULATION = 200
DEFAULT_GENERATIONS = 50
SLOW_SURROGATE_GENERATIONS = 15


def evidence_notice(value: str) -> str:
    """Return the fixed human-facing boundary for one evidence class."""

    if value == "structural":
        return (
            "Structural-only evidence: this benchmark validates workflow and integration "
            "behavior and must not support algorithm performance conclusions."
        )
    if value == "performance":
        return (
            "Performance evidence is descriptive only: the benchmark does not rank "
            "strategies or make scientific acceptance decisions."
        )
    return "Unclassified evidence; do not use it for performance conclusions."


def replication_scope(evidence: str, seed_count: int) -> str:
    """Classify how explicitly configured seeds bound result interpretation."""

    if evidence != "performance":
        return "structural"
    if seed_count <= 0:
        return "unclassified"
    return "exploratory" if seed_count == 1 else "multi-seed"


def replication_notice(value: str) -> str:
    """Return the fixed interpretation boundary for one replication scope."""

    if value == "exploratory":
        return (
            "Exploratory single-seed performance evidence: suitable for fast "
            "algorithm iteration, not a robust multi-seed conclusion."
        )
    if value == "multi-seed":
        return (
            "Multi-seed descriptive performance evidence: seed count is explicitly "
            "configurable, and the benchmark does not infer significance or robustness."
        )
    if value == "structural":
        return (
            "Seed replication is not a performance claim for structural-only evidence."
        )
    return "Unclassified replication scope; do not infer a robust conclusion."


class BenchmarkError(RuntimeError):
    """A user-actionable benchmark contract error."""


class BenchmarkStorageError(BenchmarkError):
    """A campaign-fatal failure to persist benchmark evidence."""


def freeze_json(value: Any) -> Any:
    """Recursively freeze a JSON-compatible value."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    """Return mutable JSON-compatible containers from a frozen value."""

    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(frozen=True)
class BaselineManifest:
    id: str
    name: str
    description: str
    root: Path
    workspace: Path
    execution: Mapping[str, Any]
    contract: Mapping[str, Any]
    estimates: Mapping[str, Any]
    materialize_excludes: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "format": BASELINE_FORMAT,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": str(self.root),
            "workspace": str(self.workspace.relative_to(self.root)),
            "execution": thaw_json(self.execution),
            "contract": thaw_json(self.contract),
            "estimates": thaw_json(self.estimates),
            "materialize_excludes": list(self.materialize_excludes),
        }


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    source: Path | None
    sources: Mapping[str, Path]
    slow_surrogate: bool = False

    def source_for(self, baseline_id: str) -> Path:
        selected = self.sources.get(baseline_id, self.source)
        if selected is None:
            raise BenchmarkError(
                f"strategy {self.id!r} has no source for baseline {baseline_id!r}"
            )
        return Path(selected)


@dataclass(frozen=True)
class ComparisonSpec:
    id: str
    baseline_ids: tuple[str, ...]
    strategy_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    population: int | None
    generations: int | None
    reference: str | None
    contains_slow_surrogate: bool = False
    stop_on_top10_reference: bool = False


@dataclass(frozen=True)
class PostprocessorSpec:
    id: str
    callback: str


@dataclass(frozen=True)
class WorkflowRequest:
    name: str
    evidence: str
    strategies: tuple[StrategySpec, ...]
    comparisons: tuple[ComparisonSpec, ...]
    postprocessors: tuple[PostprocessorSpec, ...]
    fail_fast: bool
    cell_concurrency: int
    representative_generation_seconds: float | None
    budget_profile: str
    preset: Mapping[str, Any]
    python: Path
    workspace: Path
    source: Path


@dataclass(frozen=True)
class CellSpec:
    id: str
    display_label: str
    comparison_id: str
    baseline_id: str
    strategy_id: str
    seed: int
    population: int
    generations: int
    evidence: str
    replication_scope: str
    contains_slow_surrogate: bool
    representative_generation_seconds: float | None
    baseline_digest: str
    strategy_digest: str
    strategy_source: Path
    strategy_files: Mapping[str, Path]
    execution: Mapping[str, Any]
    contract: Mapping[str, Any]
    top10_reference: str | None = None

    @property
    def planned_evaluations(self) -> int:
        return self.population * self.generations

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_label": self.display_label,
            "comparison": self.comparison_id,
            "baseline": self.baseline_id,
            "strategy": self.strategy_id,
            "seed": self.seed,
            "population": self.population,
            "generations": self.generations,
            "evidence": self.evidence,
            "replication_scope": self.replication_scope,
            "contains_slow_surrogate": self.contains_slow_surrogate,
            "representative_generation_seconds": (
                self.representative_generation_seconds
            ),
            "planned_evaluations": self.planned_evaluations,
            "baseline_digest": self.baseline_digest,
            "strategy_digest": self.strategy_digest,
            "strategy_source": str(self.strategy_source),
            "strategy_files": {
                relative: str(source)
                for relative, source in self.strategy_files.items()
            },
            "execution": thaw_json(self.execution),
            "contract": thaw_json(self.contract),
            "top10_reference": self.top10_reference,
        }


@dataclass(frozen=True)
class RunSpec:
    """The complete, expanded plan for the workspace's single execution."""

    workflow: WorkflowRequest
    baselines: tuple[BaselineManifest, ...]
    cells: tuple[CellSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        strategies = [
            {
                "id": item.id,
                "name": item.name,
                "source": None if item.source is None else str(item.source),
                "sources": {
                    key: str(value) for key, value in sorted(item.sources.items())
                },
                "slow_surrogate": item.slow_surrogate,
            }
            for item in self.workflow.strategies
        ]
        comparisons = []
        for item in self.workflow.comparisons:
            if item.population is None or item.generations is None:
                raise BenchmarkError(f"comparison {item.id!r} budget is unresolved")
            scope = replication_scope(self.workflow.evidence, len(item.seeds))
            comparisons.append(
                {
                    "id": item.id,
                    "baselines": list(item.baseline_ids),
                    "strategies": list(item.strategy_ids),
                    "seeds": list(item.seeds),
                    "population": item.population,
                    "generations": item.generations,
                    "contains_slow_surrogate": item.contains_slow_surrogate,
                    "replication_scope": scope,
                    "replication_notice": replication_notice(scope),
                    "reference": item.reference,
                    "stop_on_top10_reference": item.stop_on_top10_reference,
                }
            )
        return {
            "format": SPEC_FORMAT,
            "workflow": {
                "format": WORKFLOW_FORMAT,
                "name": self.workflow.name,
                "evidence": self.workflow.evidence,
                "workspace": str(self.workflow.workspace),
                "source": str(self.workflow.source),
                "strategies": strategies,
                "comparisons": comparisons,
                "postprocessors": [
                    {"id": item.id, "callback": item.callback}
                    for item in self.workflow.postprocessors
                ],
                "fail_fast": self.workflow.fail_fast,
                "cell_concurrency": self.workflow.cell_concurrency,
                "representative_generation_seconds": (
                    self.workflow.representative_generation_seconds
                ),
                "budget_profile": self.workflow.budget_profile,
                "preset": thaw_json(self.workflow.preset),
                "python": str(self.workflow.python),
            },
            "baselines": {
                item.id: item.public_dict() for item in self.baselines
            },
            "cells": [cell.to_dict() for cell in self.cells],
        }


@dataclass(frozen=True)
class PostprocessContext:
    workspace: Path
    resources: Path
    results: Path
    visualizations: Path
    reports: Path
    temp: Path
    output: Path


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float
    timed_out: bool
    stdout: Path
    stderr: Path


def cell_display_label(
    *,
    baseline_id: str,
    baseline_name: str,
    strategy_id: str,
    strategy_name: str,
    seed: int,
) -> str:
    """Build a stable display-only identity that is never used as a path."""

    def clean(value: object) -> str:
        return " ".join(str(value).split()) or "unnamed"

    return (
        f"baseline={clean(baseline_id)} ({clean(baseline_name)}) | "
        f"strategy={clean(strategy_id)} ({clean(strategy_name)}) | "
        f"seed={int(seed)}"
    )


__all__ = [
    "BASELINE_FORMAT",
    "BUDGET_PROFILES",
    "DEFAULT_GENERATIONS",
    "DEFAULT_POPULATION",
    "DEFAULT_SEED",
    "DEFAULT_SEEDS",
    "EVIDENCE_CLASSES",
    "SLOW_SURROGATE_GENERATIONS",
    "SPEC_FORMAT",
    "STATE_FORMAT",
    "WORKFLOW_FORMAT",
    "WORKSPACE_FORMAT",
    "BaselineManifest",
    "BenchmarkError",
    "BenchmarkStorageError",
    "CellSpec",
    "CommandResult",
    "ComparisonSpec",
    "PostprocessContext",
    "PostprocessorSpec",
    "RunSpec",
    "StrategySpec",
    "WorkflowRequest",
    "cell_display_label",
    "freeze_json",
    "evidence_notice",
    "replication_notice",
    "replication_scope",
    "thaw_json",
]
