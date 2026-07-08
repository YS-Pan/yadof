from __future__ import annotations

from dataclasses import dataclass, field
import random

from project import config

from .gpsaf_pymoo import (
    baseline_records,
    diagnostics as pymoo_diagnostics,
    make_context,
    population_from_records,
    resolve_problem_info,
)
from .gpsaf_misc import (
    Population,
    Costs,
    evaluate,
    history_records,
)
from .gpsaf_phases import ensure_surrogate_fresh_enough, notify_surrogate_after_submission, surrogate_population


@dataclass(frozen=True)
class OptimizationResult:
    generation_index: int
    population: Population
    costs: Costs
    history_count: int
    source: str
    surrogate_used: bool = False
    diagnostics: dict[str, object] = field(default_factory=dict)


def _config_population_size(population_size: int | None) -> int:
    return int(population_size or config.OPTIMIZE_POPULATION_SIZE)


def _config_seed(random_seed: int | None) -> int:
    return int(config.OPTIMIZE_RANDOM_SEED if random_seed is None else random_seed)


def _surrogate_requested() -> bool:
    alpha = int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1))
    beta = int(getattr(config, "OPTIMIZE_SURROGATE_BETA", 0))
    return alpha > 1 or beta > 0


def run_one_generation(
    *,
    generation_index: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
) -> OptimizationResult:
    size = _config_population_size(population_size)
    seed = _config_seed(random_seed)
    history = history_records()
    problem = resolve_problem_info(variable_count, history)
    context = make_context(problem, population_size=size, seed=seed, generation_index=int(generation_index))
    diagnostics: dict[str, object] = pymoo_diagnostics(context)
    diagnostics.update(
        {
            "surrogate_alpha": int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1)),
            "surrogate_beta": int(getattr(config, "OPTIMIZE_SURROGATE_BETA", 0)),
            "surrogate_gamma": float(getattr(config, "OPTIMIZE_SURROGATE_GAMMA", 0.5)),
        }
    )
    surrogate_used = False
    rng = random.Random(seed + int(generation_index) * 1009)
    source = "gpsaf_random"

    if history and _surrogate_requested():
        diagnostics.update(ensure_surrogate_fresh_enough(int(generation_index)))
        population, surrogate_info = surrogate_population(
            history,
            context=context,
            generation_index=int(generation_index),
            population_size=size,
            seed=seed,
        )
        diagnostics.update(surrogate_info)
        if population is None:
            records, source = baseline_records(
                context=context,
                history=history,
                size=size,
                generation_index=int(generation_index),
                rng=rng,
            )
            population = population_from_records(records)
        else:
            surrogate_used = True
            source = "gpsaf_surrogate"
    else:
        if not _surrogate_requested():
            diagnostics["surrogate_mode"] = "disabled_by_gpsaf_parameters"
        elif not history:
            diagnostics["surrogate_mode"] = "warmup_no_history"
        records, source = baseline_records(
            context=context,
            history=history,
            size=size,
            generation_index=int(generation_index),
            rng=rng,
        )
        population = population_from_records(records)

    after_jobs_submitted = (
        (lambda: notify_surrogate_after_submission(int(generation_index)))
        if _surrogate_requested()
        else None
    )
    costs = evaluate(
        population,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=int(generation_index),
        after_jobs_submitted=after_jobs_submitted,
    )
    return OptimizationResult(
        generation_index=int(generation_index),
        population=population,
        costs=costs,
        history_count=len(history),
        source=source,
        surrogate_used=surrogate_used,
        diagnostics=diagnostics,
    )
