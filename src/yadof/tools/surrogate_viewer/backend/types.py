"""Data contracts shared by the integrated viewer backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable, Mapping

import numpy as np


ProgressCallback = Callable[[int, int, str], None]


class AuditCancelled(RuntimeError):
    """Raised when the user stops a cross-generation calculation."""


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AuditCancelled("cross-generation calculation stopped")


@dataclass(frozen=True)
class CheckpointInfo:
    generation: int
    path: Path
    sample_count: int
    member_count: int
    training_error: float | None
    payload: Mapping[str, object]

    @property
    def label(self) -> str:
        error = (
            ""
            if self.training_error is None
            else f" · training error {self.training_error:.4g}"
        )
        return (
            f"Generation {self.generation} · {self.sample_count} samples · "
            f"{self.member_count} members{error}"
        )


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    unit: str
    ranges: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class RealResult:
    job_name: str
    generation: int
    population_index: int | None
    raw_values: tuple[float, ...]
    normalized_values: tuple[float, ...]

    @property
    def label(self) -> str:
        position = (
            f"individual {self.population_index}"
            if self.population_index is not None
            else self.job_name
        )
        return f"Generation {self.generation} · {position} · {self.job_name}"


@dataclass(frozen=True)
class DimensionSpec:
    index: int
    name: str
    coordinates: np.ndarray
    unit: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name

    @property
    def default_value(self) -> float:
        return self.nearest_value(0.0)

    def nearest_value(self, target: float) -> float:
        value = float(target)
        if not np.isfinite(value):
            raise ValueError(f"{self.name} fixed value must be finite")
        coordinates = np.asarray(self.coordinates, dtype=float).reshape(-1)
        if coordinates.size == 0:
            raise ValueError(f"{self.name} has no coordinates")
        index = int(np.argmin(np.abs(coordinates - value)))
        return float(coordinates[index])


@dataclass(frozen=True)
class PlotData:
    name: str
    dimensions: tuple[DimensionSpec, ...]
    values: np.ndarray
    slice_label: str

    @property
    def ndim(self) -> int:
        return len(self.dimensions)


@dataclass(frozen=True)
class PlotRequest:
    item_index: int
    plotted_dimensions: tuple[int, ...]
    fixed_values: tuple[tuple[int, float], ...]

    @property
    def fixed_map(self) -> dict[int, float]:
        return {
            int(index): float(value)
            for index, value in self.fixed_values
        }


@dataclass(frozen=True)
class CurveData:
    name: str
    x: np.ndarray
    y: np.ndarray
    x_label: str
    y_label: str
    slice_label: str


@dataclass(frozen=True)
class PredictionResult:
    checkpoint_generation: int
    normalized_values: tuple[float, ...]
    raw_values: tuple[float, ...]
    predicted_sample: tuple[Mapping[str, object], ...]
    member_samples: tuple[tuple[Mapping[str, object], ...], ...]
    predicted_costs: tuple[float, ...]
    true_sample: tuple[Mapping[str, object], ...] | None = None
    true_costs: tuple[float, ...] | None = None
    true_job_name: str | None = None
    predicted_plot: PlotData | None = None
    member_plots: tuple[PlotData, ...] = ()
    plot_note: str = ""


@dataclass(frozen=True)
class ErrorMatrix:
    checkpoint_generations: tuple[int, ...]
    optimization_generations: tuple[int, ...]
    values: np.ndarray
    metric_label: str
    sample_counts: tuple[int, ...]


@dataclass(frozen=True)
class CrossGenerationErrorAudit:
    """Compact aggregates produced by one complete inference pass."""

    checkpoint_generations: tuple[int, ...]
    optimization_generations: tuple[int, ...]
    objective_names: tuple[str, ...]
    rawdata_names: tuple[str, ...]
    sample_counts: tuple[int, ...]
    relative_sums: np.ndarray
    relative_counts: np.ndarray
    absolute_sums: np.ndarray
    absolute_counts: np.ndarray
    raw_relative_sums: np.ndarray
    raw_relative_counts: np.ndarray
    raw_absolute_sums: np.ndarray
    raw_absolute_counts: np.ndarray
    sample_fraction: float

    @property
    def memory_bytes(self) -> int:
        arrays = (
            self.relative_sums,
            self.relative_counts,
            self.absolute_sums,
            self.absolute_counts,
            self.raw_relative_sums,
            self.raw_relative_counts,
            self.raw_absolute_sums,
            self.raw_absolute_counts,
        )
        return sum(array.nbytes for array in arrays)

    def matrix(
        self,
        *,
        metric: str = "relative",
        quantity_kind: str = "cost",
        quantity_index: int | None = None,
    ) -> ErrorMatrix:
        """Derive a display matrix from cached sums and counts."""

        if metric not in {"relative", "absolute"}:
            raise ValueError("metric must be 'relative' or 'absolute'")
        if quantity_kind not in {"cost", "rawdata"}:
            raise ValueError("quantity_kind must be 'cost' or 'rawdata'")

        if quantity_kind == "cost":
            names = self.objective_names
            sums = (
                self.relative_sums
                if metric == "relative"
                else self.absolute_sums
            )
            counts = (
                self.relative_counts
                if metric == "relative"
                else self.absolute_counts
            )
            all_label = "all costs"
        else:
            names = self.rawdata_names
            sums = (
                self.raw_relative_sums
                if metric == "relative"
                else self.raw_absolute_sums
            )
            counts = (
                self.raw_relative_counts
                if metric == "relative"
                else self.raw_absolute_counts
            )
            all_label = "all rawData"

        if quantity_index is None:
            selected_sums = np.sum(sums, axis=2)
            selected_counts = np.sum(counts, axis=2)
            quantity_label = all_label
        else:
            index = int(quantity_index)
            if not 0 <= index < len(names):
                raise IndexError(index)
            selected_sums = sums[:, :, index]
            selected_counts = counts[:, :, index]
            prefix = "cost" if quantity_kind == "cost" else "rawData"
            quantity_label = f"{prefix} · {names[index]}"

        values = np.full(selected_sums.shape, np.nan, dtype=float)
        np.divide(
            selected_sums,
            selected_counts,
            out=values,
            where=selected_counts > 0,
        )
        error_label = (
            "Mean relative error"
            if metric == "relative"
            else "Mean absolute error"
        )
        return ErrorMatrix(
            checkpoint_generations=self.checkpoint_generations,
            optimization_generations=self.optimization_generations,
            values=values,
            metric_label=f"{error_label} · {quantity_label}",
            sample_counts=self.sample_counts,
        )
