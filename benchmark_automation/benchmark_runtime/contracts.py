"""Dependency-free contracts for the source-checkout benchmark."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

BASELINE_FORMAT = "yadof.benchmark.baseline"
STUDY_FORMAT = "yadof.benchmark.study"
RUN_FORMAT = "yadof.benchmark.run"
STATE_FORMAT = "yadof.benchmark.state"

class BenchmarkError(RuntimeError):
    """A user-actionable benchmark contract error."""


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
    snapshot_excludes: tuple[str, ...] = ()

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
            "snapshot_excludes": list(self.snapshot_excludes),
        }


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    source: Path | None
    sources: Mapping[str, Path]

    def source_for(self, baseline_id: str) -> Path:
        selected = self.sources.get(baseline_id, self.source)
        if selected is None:
            raise BenchmarkError(
                f"strategy {self.id!r} has no source for baseline {baseline_id!r}"
            )
        return Path(selected)


@dataclass(frozen=True)
class StudyRequest:
    name: str
    baseline_ids: tuple[str, ...]
    strategies: tuple[StrategySpec, ...]
    seeds: tuple[int, ...]
    population: int
    generations: int
    reference: str | None
    fail_fast: bool
    runs_dir: Path
    python: Path
    source: Path | None = None


@dataclass(frozen=True)
class CellSpec:
    id: str
    baseline_id: str
    strategy_id: str
    seed: int
    population: int
    generations: int
    baseline_snapshot: str
    strategy_snapshot: str
    baseline_digest: str
    strategy_digest: str
    strategy_source: Path
    execution: Mapping[str, Any]
    contract: Mapping[str, Any]

    @property
    def planned_evaluations(self) -> int:
        return self.population * self.generations

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "baseline": self.baseline_id,
            "strategy": self.strategy_id,
            "seed": self.seed,
            "population": self.population,
            "generations": self.generations,
            "planned_evaluations": self.planned_evaluations,
            "baseline_snapshot": self.baseline_snapshot,
            "strategy_snapshot": self.strategy_snapshot,
            "baseline_digest": self.baseline_digest,
            "strategy_digest": self.strategy_digest,
            "strategy_source": str(self.strategy_source),
            "execution": thaw_json(self.execution),
            "contract": thaw_json(self.contract),
        }


@dataclass(frozen=True)
class RunSpec:
    study: StudyRequest
    baselines: tuple[BaselineManifest, ...]
    cells: tuple[CellSpec, ...]
    driver_digest: str
    digest: str

    def to_dict(self) -> dict[str, Any]:
        strategies = []
        for item in self.study.strategies:
            strategies.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "source": None if item.source is None else str(item.source),
                    "sources": {
                        key: str(value) for key, value in sorted(item.sources.items())
                    },
                }
            )
        return {
            "format": RUN_FORMAT,
            "digest": self.digest,
            "driver_digest": self.driver_digest,
            "study": {
                "name": self.study.name,
                "source": None if self.study.source is None else str(self.study.source),
                "baselines": list(self.study.baseline_ids),
                "strategies": strategies,
                "seeds": list(self.study.seeds),
                "population": self.study.population,
                "generations": self.study.generations,
                "reference": self.study.reference,
                "fail_fast": self.study.fail_fast,
                "runs_dir": str(self.study.runs_dir),
                "python": str(self.study.python),
            },
            "baselines": {
                item.id: item.public_dict() for item in self.baselines
            },
            "cells": [cell.to_dict() for cell in self.cells],
        }


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float
    timed_out: bool
    stdout: Path
    stderr: Path


__all__ = [
    "BASELINE_FORMAT",
    "RUN_FORMAT",
    "STATE_FORMAT",
    "STUDY_FORMAT",
    "BaselineManifest",
    "BenchmarkError",
    "CellSpec",
    "CommandResult",
    "RunSpec",
    "StrategySpec",
    "StudyRequest",
    "freeze_json",
    "thaw_json",
]
