from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ...surrogate.training import (
    DeterministicSurrogateComponent,
    SurrogateTrainingData,
    assess_surrogate_selection_freshness,
)
from ..primitives import full_real_search
from ..strategy import GenerationContext
from .phases import surrogate_population
from .settings import GPSAFSettings
from .errors import GPSAFErrorState


@dataclass(frozen=True, slots=True)
class GPSAFGenerationSelection:
    """One generation-local GPSAF selection awaiting real evaluation."""

    population: tuple[tuple[float, ...], ...]
    source: str
    surrogate_used: bool
    diagnostics: Mapping[str, object]
    predicted_costs: tuple[tuple[float, ...] | None, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "population",
            tuple(tuple(float(value) for value in row) for row in self.population),
        )
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "surrogate_used", bool(self.surrogate_used))
        object.__setattr__(
            self,
            "diagnostics",
            MappingProxyType(dict(self.diagnostics)),
        )


def _surrogate_requested(settings: GPSAFSettings) -> bool:
    return settings.alpha > 1 or settings.beta > 0


def select_gpsaf_generation(
    generation: GenerationContext,
    *,
    search,
    surrogate: DeterministicSurrogateComponent,
    settings: GPSAFSettings,
    training_data: SurrogateTrainingData,
    error_state: GPSAFErrorState | None = None,
) -> GPSAFGenerationSelection:
    """Select real candidates without owning evaluation, training, or commit."""

    if not isinstance(training_data, SurrogateTrainingData):
        raise TypeError("GPSAF selection requires explicit SurrogateTrainingData")
    if not isinstance(surrogate, DeterministicSurrogateComponent):
        raise TypeError(
            "GPSAF selection requires a DeterministicSurrogateComponent"
        )
    search.validate(generation.config, generation.problem)
    surrogate.validate(generation.config, generation.problem)

    size = generation.population_size
    seed = generation.random_seed
    history = generation.history
    errors = error_state if error_state is not None else GPSAFErrorState()
    error_scales = errors.for_interpretation(generation.snapshot.interpretation_fingerprint)
    diagnostics: dict[str, object] = {
        "surrogate_alpha": settings.alpha,
        "surrogate_beta": settings.beta,
        "surrogate_gamma": settings.gamma,
        "exploration_fraction": settings.exploration_fraction,
        "infill_selection": settings.infill_selection,
        "surrogate_training_content_digest": training_data.content_digest,
        "surrogate_training_provenance_digest": training_data.provenance_digest,
        "surrogate_training_row_ids": training_data.row_ids,
        "surrogate_component": dict(
            surrogate.semantic_identity(generation.config, generation.problem)
        ),
        **errors.diagnostics(),
    }
    surrogate_used = False
    source = "gpsaf_random"

    if history and _surrogate_requested(settings):
        freshness = assess_surrogate_selection_freshness(
            surrogate,
            generation,
            training_data,
        )
        diagnostics.update(freshness.diagnostics())
        if freshness.ready:
            population, surrogate_info = surrogate_population(
                history,
                generation_context=generation,
                search=search,
                surrogate=surrogate,
                generation_index=generation.generation_index,
                population_size=size,
                seed=seed,
                settings=settings,
                training_data=training_data,
                error_scales=error_scales,
            )
        else:
            population = None
            surrogate_info = {
                "surrogate_error": "no_fresh_trained_surrogate",
                "surrogate_mode": "waiting_for_explicit_training",
            }
        diagnostics.update(surrogate_info)
        if population is None:
            selected = full_real_search(
                generation,
                search,
                population_size=size,
                algorithm_seed=seed,
                random_seed=seed + generation.generation_index * 1009,
                origin_prefix="gpsaf",
            )
            population = selected.population
            source = selected.source
            diagnostics.update(dict(selected.state.diagnostics))
            diagnostics.update(dict(selected.diagnostics))
        else:
            surrogate_used = True
            source = "gpsaf_surrogate"
    else:
        if not _surrogate_requested(settings):
            diagnostics["surrogate_mode"] = "disabled_by_gpsaf_parameters"
        elif not history:
            diagnostics["surrogate_mode"] = "warmup_no_history"
        selected = full_real_search(
            generation,
            search,
            population_size=size,
            algorithm_seed=seed,
            random_seed=seed + generation.generation_index * 1009,
            origin_prefix="gpsaf",
        )
        population = selected.population
        source = selected.source
        diagnostics.update(dict(selected.state.diagnostics))
        diagnostics.update(dict(selected.diagnostics))

    predicted_costs = diagnostics.pop("_prediction_rows", ())
    return GPSAFGenerationSelection(
        population=population,
        source=source,
        surrogate_used=surrogate_used,
        diagnostics=diagnostics,
        predicted_costs=predicted_costs,
    )


def start_explicit_surrogate_training(
    surrogate: DeterministicSurrogateComponent,
    context: GenerationContext,
    training_data: SurrogateTrainingData,
    *,
    enabled: bool = True,
) -> dict[str, object]:
    """Launch training after evaluation start from immutable prior evidence."""

    if not enabled:
        return {"surrogate_training_start": "disabled"}
    if not isinstance(surrogate, DeterministicSurrogateComponent):
        raise TypeError("training requires a DeterministicSurrogateComponent")
    if not isinstance(training_data, SurrogateTrainingData):
        raise TypeError("training requires explicit SurrogateTrainingData")
    try:
        status = surrogate.start_training(context, training_data)
    except Exception as exc:  # noqa: BLE001 - real evaluation remains authoritative.
        return {
            "surrogate_training_start": "failed",
            "surrogate_training_start_error": f"{exc.__class__.__name__}: {exc}",
        }
    return {
        "surrogate_training_start": str(status.action),
        "surrogate_training_pending_generation": status.pending_generation_index,
        "surrogate_training_start_error": str(status.error),
    }


def finish_explicit_surrogate_training(
    surrogate: DeterministicSurrogateComponent,
    context: GenerationContext,
    *,
    enabled: bool = True,
) -> dict[str, object]:
    """Join the explicit training request before the generation commits."""

    if not enabled:
        return {"surrogate_training_finish": "disabled"}
    if not isinstance(surrogate, DeterministicSurrogateComponent):
        raise TypeError("training requires a DeterministicSurrogateComponent")
    try:
        status = surrogate.finish_training(context)
    except Exception as exc:  # noqa: BLE001 - typed fallback remains generation-local.
        return {
            "surrogate_training_finish": "failed",
            "surrogate_training_finish_error": f"{exc.__class__.__name__}: {exc}",
        }
    return {
        "surrogate_training_finish": str(status.action),
        "surrogate_training_finish_error": str(status.error),
    }


__all__ = [
    "GPSAFGenerationSelection",
    "finish_explicit_surrogate_training",
    "select_gpsaf_generation",
    "start_explicit_surrogate_training",
]
