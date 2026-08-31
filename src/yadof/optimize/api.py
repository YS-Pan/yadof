from __future__ import annotations

import os
from typing import Mapping

from ..workspace import WorkspaceContext
from .program import execute_frozen_program, freeze_workspace_program
from .strategy import OptimizationResult


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
    results = execute_frozen_program(
        freeze_workspace_program(workspace),
        1,
        start_generation=generation_index,
        population_size=population_size,
        variable_count=variable_count,
        random_seed=random_seed,
        run_id=run_id,
        optimization_index=optimization_index,
    )
    if len(results) != 1:
        raise RuntimeError(
            "single-generation explicit program must commit exactly one result"
        )
    return results[0]


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
    _frozen_program=None,
) -> tuple[OptimizationResult, ...]:
    frozen_program = (
        freeze_workspace_program(workspace)
        if _frozen_program is None
        else _frozen_program
    )
    return execute_frozen_program(
        frozen_program,
        generations,
        start_generation=start_generation,
        population_size=population_size,
        variable_count=variable_count,
        random_seed=random_seed,
        run_id=run_id,
        optimization_index=optimization_index,
        config_overrides=config_overrides,
        fail_on_all_infinite=fail_on_all_infinite,
    )


__all__ = [
    "AllInfiniteGenerationError",
    "OptimizationResult",
    "run_one_generation",
    "run_generations",
]
