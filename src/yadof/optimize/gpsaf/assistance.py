from __future__ import annotations

import random

from ..pymoo.backend import (
    baseline_records,
    diagnostics as pymoo_diagnostics,
    make_context,
    population_from_records,
)
from ..strategy import GenerationContext, OptimizationResult, evaluate_population
from .phases import (
    ensure_surrogate_fresh_enough,
    finish_surrogate_training,
    materialize_surrogate_training_data,
    notify_surrogate_after_submission,
    surrogate_population,
)
from .settings import GPSAFSettings


def _surrogate_requested(settings: GPSAFSettings) -> bool:
    return settings.alpha > 1 or settings.beta > 0


def run_generation(
    generation: GenerationContext,
    *,
    search,
    surrogate,
    settings: GPSAFSettings,
) -> OptimizationResult:
    config = generation.config
    size = generation.population_size
    seed = generation.random_seed
    history = generation.history
    context = make_context(
        config,
        generation.problem,
        population_size=size,
        seed=seed,
        generation_index=generation.generation_index,
        search_algorithm=search.resolve_algorithm(
            generation.problem.objective_count
        ),
        search_settings=search.backend_settings(
            generation.problem.objective_count
        ),
    )
    diagnostics: dict[str, object] = pymoo_diagnostics(context)
    diagnostics.update(
        {
            "surrogate_alpha": settings.alpha,
            "surrogate_beta": settings.beta,
            "surrogate_gamma": settings.gamma,
        }
    )
    surrogate_used = False
    rng = random.Random(seed + generation.generation_index * 1009)
    source = "gpsaf_random"
    explicit_training_data = None

    if history and _surrogate_requested(settings):
        try:
            explicit_training_data = materialize_surrogate_training_data(
                surrogate, generation
            )
        except Exception as exc:  # noqa: BLE001 - explicit data failure falls back to real search.
            diagnostics.update(
                {
                    "surrogate_training_data": "failed",
                    "surrogate_training_data_error": f"{exc.__class__.__name__}: {exc}",
                }
            )
        else:
            diagnostics.update(
                ensure_surrogate_fresh_enough(
                    surrogate,
                    generation,
                    explicit_training_data,
                )
            )
        population, surrogate_info = surrogate_population(
            history,
            context=context,
            generation_context=generation,
            surrogate=surrogate,
            generation_index=generation.generation_index,
            population_size=size,
            seed=seed,
            settings=settings,
            training_data=explicit_training_data,
        )
        diagnostics.update(surrogate_info)
        if population is None:
            records, source = baseline_records(
                context=context,
                history=history,
                size=size,
                generation_index=generation.generation_index,
                rng=rng,
            )
            population = population_from_records(records)
        else:
            surrogate_used = True
            source = "gpsaf_surrogate"
    else:
        if not _surrogate_requested(settings):
            diagnostics["surrogate_mode"] = "disabled_by_gpsaf_parameters"
        elif not history:
            diagnostics["surrogate_mode"] = "warmup_no_history"
        records, source = baseline_records(
            context=context,
            history=history,
            size=size,
            generation_index=generation.generation_index,
            rng=rng,
        )
        population = population_from_records(records)

    after_jobs_submitted = (
        (
            lambda: notify_surrogate_after_submission(
                surrogate,
                generation,
            )
        )
        if _surrogate_requested(settings)
        else None
    )
    costs = evaluate_population(
        generation,
        population,
        after_jobs_submitted=after_jobs_submitted,
    )
    diagnostics.update(finish_surrogate_training(surrogate, generation))
    return OptimizationResult(
        generation_index=generation.generation_index,
        population=population,
        costs=costs,
        history_count=len(history),
        source=source,
        surrogate_used=surrogate_used,
        diagnostics=diagnostics,
    )


__all__ = ["run_generation"]
