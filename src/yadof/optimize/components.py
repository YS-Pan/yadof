"""Small composable optimization components exposed to workspace strategies."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Mapping, Protocol

from ..config import LoadedConfig
from .problem_info import ProblemInfo
from .gpsaf.settings import GPSAFSettings, create_settings as create_gpsaf_settings
from .pymoo.settings import PymooSearchSettings, create_settings as create_pymoo_settings
from .strategy import GenerationContext, OptimizationResult, evaluate_population


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


@dataclass(frozen=True, slots=True)
class GPSAFStrategy:
    search: SearchComponent
    surrogate: object
    settings: GPSAFSettings

    def validate(self, config: LoadedConfig, problem: ProblemInfo) -> None:
        self.search.validate(config, problem)
        validate = getattr(self.surrogate, "validate", None)
        if not callable(validate):
            raise TypeError("GPSAF surrogate component must define validate()")
        validate(config, problem)

    def semantic_identity(
        self,
        config: LoadedConfig,
        problem: ProblemInfo,
    ) -> Mapping[str, object]:
        identity = getattr(self.surrogate, "semantic_identity", None)
        if not callable(identity):
            raise TypeError("GPSAF surrogate component must define semantic_identity()")
        return {
            "strategy": "gpsaf",
            "strategy_version": 1,
            "search": self.search.semantic_identity(config, problem),
            "surrogate": identity(config, problem),
            "gpsaf_parameters": {
                "alpha": self.settings.alpha,
                "beta": self.settings.beta,
                "gamma": self.settings.gamma,
                "exploration_fraction": self.settings.exploration_fraction,
                "maximum_training_lag": int(
                    config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG
                ),
            },
        }

    def run_generation(self, context: GenerationContext) -> OptimizationResult:
        from .gpsaf.assistance import run_generation

        return run_generation(
            context,
            search=self.search,
            surrogate=self.surrogate,
            settings=self.settings,
        )


@dataclass(frozen=True, slots=True)
class RealSearchStrategy:
    search: SearchComponent

    def validate(self, config: LoadedConfig, problem: ProblemInfo) -> None:
        self.search.validate(config, problem)

    def semantic_identity(
        self,
        config: LoadedConfig,
        problem: ProblemInfo,
    ) -> Mapping[str, object]:
        return {
            "strategy": "real-search",
            "strategy_version": 1,
            "search": self.search.semantic_identity(config, problem),
        }

    def run_generation(self, context: GenerationContext) -> OptimizationResult:
        import random

        from .pymoo.backend import (
            baseline_records,
            diagnostics,
            make_context,
            population_from_records,
        )

        search_context = make_context(
            context.config,
            context.problem,
            population_size=context.population_size,
            seed=context.random_seed,
            generation_index=context.generation_index,
            search_algorithm=self.search.resolve_algorithm(
                context.problem.objective_count
            ),
            search_settings=self.search.backend_settings(
                context.problem.objective_count
            ),
        )
        records, source = baseline_records(
            context=search_context,
            history=context.history,
            size=context.population_size,
            generation_index=context.generation_index,
            rng=random.Random(
                context.random_seed + context.generation_index * 1009
            ),
        )
        population = population_from_records(records)
        costs = evaluate_population(context, population)
        info = diagnostics(search_context)
        info["strategy"] = "real-search"
        return OptimizationResult(
            generation_index=context.generation_index,
            population=population,
            costs=costs,
            history_count=len(context.history),
            source=source.replace("gpsaf_", "pymoo_"),
            surrogate_used=False,
            diagnostics=info,
        )


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


def gpsaf(
    *,
    search: SearchComponent,
    surrogate: object,
    alpha: int = 3,
    beta: int = 3,
    gamma: float = 0.5,
    exploration_fraction: float = 0.10,
) -> GPSAFStrategy:
    return GPSAFStrategy(
        search=search,
        surrogate=surrogate,
        settings=create_gpsaf_settings(
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            exploration_fraction=exploration_fraction,
        ),
    )


def real_search(*, search: SearchComponent) -> RealSearchStrategy:
    return RealSearchStrategy(search=search)


__all__ = [
    "GPSAFStrategy",
    "ObjectiveCountSearch",
    "PymooSearch",
    "RealSearchStrategy",
    "SearchComponent",
    "by_objective_count",
    "gpsaf",
    "pymoo_ga",
    "pymoo_nsga3",
    "real_search",
]
