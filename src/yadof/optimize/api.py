from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from ..config import LoadedConfig, load_config
from ..workspace import WorkspaceContext
from .gpsaf import OptimizationResult
from . import gpsaf
from .runner import job_names, new_run_id, next_optimization_index, now_text, record_generation_metadata


WorkspaceLike = WorkspaceContext | str | os.PathLike[str]


class AllInfiniteGenerationError(RuntimeError):
    """Raised when an explicitly strict run produces no finite objective."""

    def __init__(self, result: OptimizationResult) -> None:
        super().__init__(
            f"generation {result.generation_index} produced no finite cost rows"
        )
        self.result = result


def run_one_generation(
    workspace: WorkspaceLike,
    *,
    generation_index: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
) -> OptimizationResult:
    config = load_config(workspace)
    if run_id is None:
        run_id = new_run_id()
    if optimization_index is None:
        optimization_index = next_optimization_index(config.workspace)
    return _run_one_generation_with_config(
        config,
        generation_index=generation_index,
        population_size=population_size,
        variable_count=variable_count,
        random_seed=random_seed,
        run_id=run_id,
        optimization_index=optimization_index,
    )


def _run_one_generation_with_config(
    config: LoadedConfig,
    *,
    generation_index: int,
    population_size: int | None,
    variable_count: int | None,
    random_seed: int | None,
    run_id: str,
    optimization_index: int,
) -> OptimizationResult:
    return gpsaf.run_one_generation(
        config,
        generation_index=int(generation_index),
        population_size=population_size,
        variable_count=variable_count,
        random_seed=random_seed,
        run_id=run_id,
        optimization_index=int(optimization_index),
    )


def run_generations(
    workspace: WorkspaceLike,
    generations: int,
    *,
    start_generation: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    config_overrides: Mapping[str, object] | None = None,
    fail_on_all_infinite: bool = False,
) -> tuple[OptimizationResult, ...]:
    initial_config = load_config(workspace, overrides=config_overrides)
    run_id = new_run_id() if run_id is None else str(run_id)
    optimization_index = (
        next_optimization_index(initial_config.workspace)
        if optimization_index is None
        else int(optimization_index)
    )
    results: list[OptimizationResult] = []
    for offset in range(max(0, int(generations))):
        # Reload once per generation so workspace config edits become visible at
        # the same boundary as evaluator/task edits.
        config = load_config(workspace, overrides=config_overrides)
        generation_index = int(start_generation) + offset
        _progress(f"generation {generation_index}: start")
        started_at = now_text()
        before = job_names(config.workspace)
        result = _run_one_generation_with_config(
            config,
            generation_index=generation_index,
            population_size=population_size,
            variable_count=variable_count,
            random_seed=random_seed,
            run_id=run_id,
            optimization_index=optimization_index,
        )
        ended_at = now_text()
        after = job_names(config.workspace)
        record_generation_metadata(
            config.workspace,
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
        if fail_on_all_infinite and _all_infinite(result.costs):
            raise AllInfiniteGenerationError(result)
    return tuple(results)


def _all_infinite(costs) -> bool:
    import math

    rows = tuple(tuple(float(value) for value in row) for row in costs)
    return bool(rows) and not any(
        math.isfinite(value) for row in rows for value in row
    )


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)


__all__ = [
    "AllInfiniteGenerationError",
    "OptimizationResult",
    "run_one_generation",
    "run_generations",
]
