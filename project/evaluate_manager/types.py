from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JobSpec:
    name: str
    directory: Path
    unnormalized_variables: tuple[float, ...]
    normalized_variables: tuple[float, ...] = ()
    run_id: str | None = None
    optimization_index: int | None = None
    generation_index: int | None = None
    population_index: int | None = None


@dataclass(frozen=True)
class JobResult:
    job_name: str
    job_dir: Path
    status: str
    unnormalized_variables: tuple[float, ...]
    raw_data_paths: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    costs: tuple[float, ...] | None = None
