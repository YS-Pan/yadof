from __future__ import annotations

import os

from .gpsaf import OptimizationResult
from . import gpsaf
from .runner import job_names, new_run_id, next_optimization_index, now_text, record_generation_metadata


def run_one_generation(
    *,
    generation_index: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
) -> OptimizationResult:
    if run_id is None:
        run_id = new_run_id()
    if optimization_index is None:
        optimization_index = next_optimization_index()
    return gpsaf.run_one_generation(
        generation_index=int(generation_index),
        population_size=population_size,
        variable_count=variable_count,
        random_seed=random_seed,
        run_id=run_id,
        optimization_index=int(optimization_index),
    )


def run_generations(
    generations: int,
    *,
    start_generation: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
) -> tuple[OptimizationResult, ...]:
    run_id = new_run_id() if run_id is None else str(run_id)
    optimization_index = next_optimization_index() if optimization_index is None else int(optimization_index)
    results: list[OptimizationResult] = []
    for offset in range(max(0, int(generations))):
        generation_index = int(start_generation) + offset
        _progress(f"generation {generation_index}: start")
        started_at = now_text()
        before = job_names()
        result = run_one_generation(
            generation_index=generation_index,
            population_size=population_size,
            variable_count=variable_count,
            random_seed=random_seed,
            run_id=run_id,
            optimization_index=optimization_index,
        )
        ended_at = now_text()
        after = job_names()
        record_generation_metadata(
            run_id=run_id,
            optimization_index=optimization_index,
            result=result,
            started_at=started_at,
            ended_at=ended_at,
            jobs_before=before,
            jobs_after=after,
        )
        results.append(result)
        _progress(f"generation {generation_index}: finished")
    return tuple(results)


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)


__all__ = ["OptimizationResult", "run_one_generation", "run_generations"]
