from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..job_template import NamedRawDataItem


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
    job_dir: Path | None
    status: str
    unnormalized_variables: tuple[float, ...]
    normalized_variables: tuple[float, ...] = ()
    raw_data_paths: tuple[Path, ...] = ()
    raw_data_items: tuple[NamedRawDataItem, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    costs: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """One input-ordered batch after durable evidence finalization."""

    batch_id: str
    mode: str
    rows: tuple[JobResult, ...]
    objective_width: int
    cancel_requested: bool = False
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        batch_id = str(self.batch_id).strip()
        mode = str(self.mode).strip().lower()
        width = int(self.objective_width)
        if not batch_id:
            raise ValueError("batch_id must be non-empty")
        if mode not in {"fast", "local", "distributed"}:
            raise ValueError(f"unsupported evaluation mode: {mode!r}")
        if width <= 0:
            raise ValueError("objective_width must be positive")
        object.__setattr__(self, "batch_id", batch_id)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(
            self,
            "rows",
            tuple(
                replace(row, metadata=_freeze_mapping(row.metadata))
                for row in self.rows
            ),
        )
        object.__setattr__(self, "objective_width", width)
        object.__setattr__(
            self,
            "diagnostics",
            _freeze_mapping(self.diagnostics),
        )

    @property
    def costs(self) -> tuple[tuple[float, ...], ...]:
        """Return optimizer-shaped costs, mapping only missing row costs to inf."""

        fallback = tuple(math.inf for _ in range(self.objective_width))
        return tuple(
            tuple(float(value) for value in row.costs)
            if row.costs is not None
            else fallback
            for row in self.rows
        )

    @property
    def cancelled(self) -> bool:
        return any(row.status == "cancelled" for row in self.rows)


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): _freeze_value(item) for key, item in value.items()}
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    return value
