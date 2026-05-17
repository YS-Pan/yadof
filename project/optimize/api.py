from __future__ import annotations

from .gpsaf import OptimizationResult
from . import gpsaf
from .runner import job_names, new_run_id, now_text, record_generation_metadata


def run_one_generation(
    *,
    generation_index: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
) -> OptimizationResult:
    return gpsaf.run_one_generation(
        generation_index=int(generation_index),
        population_size=population_size,
        variable_count=variable_count,
        random_seed=random_seed,
    )


def run_generations(
    generations: int,
    *,
    start_generation: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
) -> tuple[OptimizationResult, ...]:
    run_id = new_run_id() if run_id is None else str(run_id)
    results: list[OptimizationResult] = []
    for offset in range(max(0, int(generations))):
        generation_index = int(start_generation) + offset
        started_at = now_text()
        before = job_names()
        result = run_one_generation(
            generation_index=generation_index,
            population_size=population_size,
            variable_count=variable_count,
            random_seed=random_seed,
        )
        ended_at = now_text()
        after = job_names()
        record_generation_metadata(
            run_id=run_id,
            result=result,
            started_at=started_at,
            ended_at=ended_at,
            jobs_before=before,
            jobs_after=after,
        )
        results.append(result)
    return tuple(results)


__all__ = ["OptimizationResult", "run_one_generation", "run_generations"]
