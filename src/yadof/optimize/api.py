from __future__ import annotations

from dataclasses import replace
import os
from typing import Mapping

from ..config import LoadedConfig, load_config
from ..recorded_data.session import CampaignSession
from ..task_snapshot import GenerationTaskSnapshot
from ..workspace import WorkspaceContext
from .runner import new_run_id, next_optimization_index, now_text, record_generation_metadata
from .state import read_active_strategy_state, write_active_strategy_state
from .strategy import (
    GenerationContext,
    OptimizationResult,
    history_records,
    load_workspace_strategy,
    resolve_problem_info,
)


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
    session = CampaignSession(config)
    try:
        snapshot = session.begin_generation(config)
        started_at = now_text()
        before = _session_job_names(session)
        result = _run_one_generation_with_config(
            snapshot.config,
            generation_index=generation_index,
            population_size=population_size,
            variable_count=variable_count,
            random_seed=random_seed,
            run_id=run_id,
            optimization_index=optimization_index,
            session=session,
            snapshot=snapshot,
        )
        ended_at = now_text()
        after = _session_job_names(session)
        result = _with_recording_diagnostics(result, session, snapshot)
        record_generation_metadata(
            snapshot.config.workspace,
            run_id=run_id,
            optimization_index=optimization_index,
            result=result,
            started_at=started_at,
            ended_at=ended_at,
            jobs_before=before,
            jobs_after=after,
            session=session,
            snapshot=snapshot,
        )
        session.finish_generation()
        return result
    finally:
        session.close()


def _run_one_generation_with_config(
    config: LoadedConfig,
    *,
    generation_index: int,
    population_size: int | None,
    variable_count: int | None,
    random_seed: int | None,
    run_id: str,
    optimization_index: int,
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
) -> OptimizationResult:
    history = history_records(
        config.workspace,
        session=session,
        snapshot=snapshot,
    )
    problem = resolve_problem_info(config.workspace, variable_count, history)
    definition = load_workspace_strategy(
        config.workspace,
        config=config,
        problem=problem,
    )

    active = read_active_strategy_state(config.workspace)
    if active is not None and active.strategy_signature != definition.signature:
        # A strategy switch is a generation boundary. Finish any work belonging
        # to the old namespace and release its in-memory model before publishing
        # the new active pointer; disk evidence remains intact.
        try:
            from ..surrogate.api import deactivate_workspace

            deactivate_workspace(config.workspace.root)
        except ImportError:
            # A selected non-surrogate strategy must remain usable in a core-only
            # environment. If the optional backend cannot import, this process
            # cannot own one of its in-memory training tasks; retained disk state
            # still remains isolated by the old strategy signature.
            pass
    write_active_strategy_state(
        config.workspace,
        strategy_signature=definition.signature,
        strategy_identity=definition.identity,
        optimization_source_hash=snapshot.optimization_fingerprint,
    )

    selected_population_size = (
        int(config.OPTIMIZE_POPULATION_SIZE)
        if population_size is None
        else int(population_size)
    )
    if selected_population_size <= 0:
        raise ValueError("population_size must be positive")
    selected_seed = (
        int(config.OPTIMIZE_RANDOM_SEED)
        if random_seed is None
        else int(random_seed)
    )
    context = GenerationContext(
        config=config,
        generation_index=int(generation_index),
        population_size=selected_population_size,
        random_seed=selected_seed,
        run_id=str(run_id),
        optimization_index=int(optimization_index),
        session=session,
        snapshot=snapshot,
        history=history,
        problem=problem,
        strategy_signature=definition.signature,
        strategy_identity=definition.identity,
    )
    result = definition.strategy.run_generation(context)
    diagnostics = dict(result.diagnostics)
    diagnostics.update(
        {
            "strategy_signature": definition.signature,
            "strategy_identity": dict(definition.identity),
            "optimization_source_hash": snapshot.optimization_fingerprint,
        }
    )
    return replace(result, diagnostics=diagnostics)


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
    session = CampaignSession(initial_config)
    try:
        for offset in range(max(0, int(generations))):
            # Reload once per generation; the session freezes recorder settings
            # and snapshots the complete task tree at this boundary.
            live_config = load_config(workspace, overrides=config_overrides)
            snapshot = session.begin_generation(live_config)
            config = snapshot.config
            generation_index = int(start_generation) + offset
            started_at = now_text()
            before = _session_job_names(session)
            result = _run_one_generation_with_config(
                config,
                generation_index=generation_index,
                population_size=population_size,
                variable_count=variable_count,
                random_seed=random_seed,
                run_id=run_id,
                optimization_index=optimization_index,
                session=session,
                snapshot=snapshot,
            )
            ended_at = now_text()
            after = _session_job_names(session)
            result = _with_recording_diagnostics(result, session, snapshot)
            record_generation_metadata(
                config.workspace,
                run_id=run_id,
                optimization_index=optimization_index,
                result=result,
                started_at=started_at,
                ended_at=ended_at,
                jobs_before=before,
                jobs_after=after,
                session=session,
                snapshot=snapshot,
            )
            session.finish_generation()
            results.append(result)
            if fail_on_all_infinite and _all_infinite(result.costs):
                raise AllInfiniteGenerationError(result)
    finally:
        final_counters = session.close()
        if results:
            diagnostics = dict(results[-1].diagnostics)
            diagnostics["recording"] = final_counters
            results[-1] = replace(results[-1], diagnostics=diagnostics)
    return tuple(results)


def _session_job_names(session: CampaignSession) -> tuple[str, ...]:
    return tuple(str(row.get("job_name", "")) for row in session.records())


def _with_recording_diagnostics(
    result: OptimizationResult,
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
) -> OptimizationResult:
    diagnostics = dict(result.diagnostics)
    diagnostics.update(
        {
            "recording": session.counters(),
            "history_reinterpretation_sec": session.last_reinterpretation_sec,
            "interpretation_fingerprint": snapshot.interpretation_fingerprint,
            "evaluation_fingerprint": snapshot.evaluation_fingerprint,
            "optimization_fingerprint": snapshot.optimization_fingerprint,
            "task_snapshot_id": snapshot.task_snapshot_id,
        }
    )
    return replace(result, diagnostics=diagnostics)


def _all_infinite(costs) -> bool:
    import math

    rows = tuple(tuple(float(value) for value in row) for row in costs)
    return bool(rows) and not any(
        math.isfinite(value) for row in rows for value in row
    )


__all__ = [
    "AllInfiniteGenerationError",
    "OptimizationResult",
    "run_one_generation",
    "run_generations",
]
