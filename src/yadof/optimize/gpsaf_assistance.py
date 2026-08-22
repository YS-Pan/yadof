from __future__ import annotations

import random

from .gpsaf_pymoo import (
    baseline_records,
    diagnostics as pymoo_diagnostics,
    make_context,
    population_from_records,
)
from .strategy import GenerationContext, OptimizationResult, evaluate_population
from .gpsaf_phases import ensure_surrogate_fresh_enough, notify_surrogate_after_submission, surrogate_population


def _surrogate_requested(config) -> bool:
    alpha = int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1))
    beta = int(getattr(config, "OPTIMIZE_SURROGATE_BETA", 0))
    return alpha > 1 or beta > 0


def run_generation(
    generation: GenerationContext,
    *,
    search,
    surrogate,
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
    )
    diagnostics: dict[str, object] = pymoo_diagnostics(context)
    diagnostics.update(
        {
            "surrogate_alpha": int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1)),
            "surrogate_beta": int(getattr(config, "OPTIMIZE_SURROGATE_BETA", 0)),
            "surrogate_gamma": float(getattr(config, "OPTIMIZE_SURROGATE_GAMMA", 0.5)),
        }
    )
    surrogate_used = False
    rng = random.Random(seed + generation.generation_index * 1009)
    source = "gpsaf_random"

    if history and _surrogate_requested(config):
        diagnostics.update(
            ensure_surrogate_fresh_enough(
                surrogate,
                generation,
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
        if not _surrogate_requested(config):
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
        if _surrogate_requested(config)
        else None
    )
    costs = evaluate_population(
        generation,
        population,
        after_jobs_submitted=after_jobs_submitted,
    )
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
