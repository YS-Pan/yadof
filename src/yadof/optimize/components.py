"""Small composable optimization components exposed to workspace strategies."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Mapping, Protocol

from ..config import LoadedConfig
from .problem_info import ProblemInfo
from .gpsaf.settings import GPSAFSettings, create_settings as create_gpsaf_settings
from .pymoo.settings import PymooSearchSettings, create_settings as create_pymoo_settings


class SearchComponent(Protocol):
    def validate(self, config: LoadedConfig, problem: ProblemInfo) -> None: ...

    def resolve_algorithm(self, objective_count: int) -> str: ...

    def backend_settings(self, objective_count: int) -> PymooSearchSettings: ...

    def semantic_identity(
        self,
        config: LoadedConfig,
        problem: ProblemInfo,
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class PymooSearch:
    algorithm: str
    settings: PymooSearchSettings

    def validate(self, config: LoadedConfig, problem: ProblemInfo) -> None:
        del config
        selected = self.resolve_algorithm(problem.objective_count)
        if selected == "ga" and int(problem.objective_count) != 1:
            raise ValueError("pymoo GA requires exactly one objective")
        if selected == "nsga3" and int(problem.objective_count) < 2:
            raise ValueError("pymoo NSGA-III requires at least two objectives")
        try:
            metadata.version("pymoo")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "the selected optimization strategy requires the declared pymoo dependency"
            ) from exc

    def resolve_algorithm(self, objective_count: int) -> str:
        del objective_count
        selected = str(self.algorithm).strip().lower()
        if selected not in {"ga", "nsga3"}:
            raise ValueError(f"unsupported pymoo search algorithm: {self.algorithm!r}")
        return selected

    def backend_settings(self, objective_count: int) -> PymooSearchSettings:
        del objective_count
        return self.settings

    def semantic_identity(
        self,
        config: LoadedConfig,
        problem: ProblemInfo,
    ) -> Mapping[str, object]:
        selected = self.resolve_algorithm(problem.objective_count)
        controlled: dict[str, object] = {
            "population_size": int(config.OPTIMIZE_POPULATION_SIZE),
            "crossover_probability": self.settings.crossover_probability,
            "mutation_probability": self.settings.mutation_probability,
            "crossover_eta": self.settings.crossover_eta,
            "mutation_eta": self.settings.mutation_eta,
            "mutated_dimensions_per_individual": self.settings.mutated_dimensions_per_individual,
            "refill_attempts": self.settings.refill_attempts,
            "archive_key_decimals": int(config.OPTIMIZE_ARCHIVE_KEY_DECIMALS),
        }
        if selected == "nsga3":
            controlled.update(
                {
                    "reference_direction_method": self.settings.reference_direction_method,
                    "reference_direction_partitions": self.settings.reference_direction_partitions,
                }
            )
        return {
            "component": "pymoo-search",
            "adapter_version": 1,
            "backend_distribution": "pymoo",
            "backend_version": metadata.version("pymoo"),
            "algorithm": selected,
            "controlled_parameters": controlled,
        }


@dataclass(frozen=True, slots=True)
class ObjectiveCountSearch:
    single: SearchComponent
    multi: SearchComponent

    def _selected(self, objective_count: int) -> SearchComponent:
        return self.single if int(objective_count) == 1 else self.multi

    def validate(self, config: LoadedConfig, problem: ProblemInfo) -> None:
        self._selected(problem.objective_count).validate(config, problem)

    def resolve_algorithm(self, objective_count: int) -> str:
        return self._selected(objective_count).resolve_algorithm(objective_count)

    def backend_settings(self, objective_count: int) -> PymooSearchSettings:
        return self._selected(objective_count).backend_settings(objective_count)

    def semantic_identity(
        self,
        config: LoadedConfig,
        problem: ProblemInfo,
    ) -> Mapping[str, object]:
        selected = self._selected(problem.objective_count)
        return {
            "component": "objective-count-dispatch",
            "selected": selected.semantic_identity(config, problem),
        }


def pymoo_ga(
    *,
    crossover_probability: float = 0.85,
    mutation_probability: float = 0.35,
    crossover_eta: float = 10.0,
    mutation_eta: float = 10.0,
    mutated_dimensions_per_individual: int = 7,
    refill_attempts: int = 8,
) -> PymooSearch:
    return PymooSearch(
        "ga",
        create_pymoo_settings(
            "pymoo_ga",
            algorithm="ga",
            crossover_probability=crossover_probability,
            mutation_probability=mutation_probability,
            crossover_eta=crossover_eta,
            mutation_eta=mutation_eta,
            mutated_dimensions_per_individual=mutated_dimensions_per_individual,
            refill_attempts=refill_attempts,
            reference_direction_method=None,
            reference_direction_partitions=None,
        ),
    )


def pymoo_nsga3(
    *,
    crossover_probability: float = 0.85,
    mutation_probability: float = 0.35,
    crossover_eta: float = 10.0,
    mutation_eta: float = 10.0,
    mutated_dimensions_per_individual: int = 7,
    refill_attempts: int = 8,
    reference_direction_method: str = "das-dennis",
    reference_direction_partitions: int | None = None,
) -> PymooSearch:
    return PymooSearch(
        "nsga3",
        create_pymoo_settings(
            "pymoo_nsga3",
            algorithm="nsga3",
            crossover_probability=crossover_probability,
            mutation_probability=mutation_probability,
            crossover_eta=crossover_eta,
            mutation_eta=mutation_eta,
            mutated_dimensions_per_individual=mutated_dimensions_per_individual,
            refill_attempts=refill_attempts,
            reference_direction_method=reference_direction_method,
            reference_direction_partitions=reference_direction_partitions,
        ),
    )


def by_objective_count(
    *,
    single: SearchComponent,
    multi: SearchComponent,
) -> ObjectiveCountSearch:
    return ObjectiveCountSearch(single=single, multi=multi)


def gpsaf_settings(
    *,
    alpha: int = 3,
    beta: int = 3,
    gamma: float = 0.5,
    exploration_fraction: float = 0.10,
    infill_selection: str = "cluster",
) -> GPSAFSettings:
    """Build GPSAF settings, with optional history-based hypervolume infill."""

    return create_gpsaf_settings(
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        exploration_fraction=exploration_fraction,
        infill_selection=infill_selection,
    )


__all__ = [
    "ObjectiveCountSearch",
    "PymooSearch",
    "SearchComponent",
    "by_objective_count",
    "gpsaf_settings",
    "pymoo_ga",
    "pymoo_nsga3",
]
