"""Immutable pymoo search settings owned by the search component."""

from __future__ import annotations

from dataclasses import dataclass

from ..._component_settings import integer, real, text


@dataclass(frozen=True, slots=True)
class PymooSearchSettings:
    crossover_probability: float
    mutation_probability: float
    crossover_eta: float
    mutation_eta: float
    mutated_dimensions_per_individual: int
    refill_attempts: int
    reference_direction_method: str | None
    reference_direction_partitions: int | None


def create_settings(
    factory: str,
    *,
    algorithm: str,
    crossover_probability: float,
    mutation_probability: float,
    crossover_eta: float,
    mutation_eta: float,
    mutated_dimensions_per_individual: int,
    refill_attempts: int,
    reference_direction_method: str | None,
    reference_direction_partitions: int | None,
) -> PymooSearchSettings:
    selected = text(factory, "algorithm", algorithm, choices=("ga", "nsga3"))
    method = None
    partitions = None
    if selected == "nsga3":
        method = text(
            factory,
            "reference_direction_method",
            reference_direction_method,
        )
        if reference_direction_partitions is not None:
            partitions = integer(
                factory,
                "reference_direction_partitions",
                reference_direction_partitions,
                minimum=1,
            )
    return PymooSearchSettings(
        crossover_probability=real(
            factory, "crossover_probability", crossover_probability,
            minimum=0.0, maximum=1.0,
        ),
        mutation_probability=real(
            factory, "mutation_probability", mutation_probability,
            minimum=0.0, maximum=1.0,
        ),
        crossover_eta=real(
            factory, "crossover_eta", crossover_eta, minimum=0.0, minimum_open=True,
        ),
        mutation_eta=real(
            factory, "mutation_eta", mutation_eta, minimum=0.0, minimum_open=True,
        ),
        mutated_dimensions_per_individual=integer(
            factory,
            "mutated_dimensions_per_individual",
            mutated_dimensions_per_individual,
            minimum=1,
        ),
        refill_attempts=integer(
            factory, "refill_attempts", refill_attempts, minimum=1
        ),
        reference_direction_method=method,
        reference_direction_partitions=partitions,
    )


__all__ = ["PymooSearchSettings", "create_settings"]
