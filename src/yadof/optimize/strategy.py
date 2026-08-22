"""Common campaign strategy boundary and workspace-owned strategy loading."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence, runtime_checkable

from ..config import LoadedConfig, load_config
from ..evaluate_manager import api as evaluate_api
from ..job_template import api as job_template_api
from ..recorded_data import api as recorded_api
from ..recorded_data.session import CampaignSession
from ..task_loader import task_module
from ..task_snapshot import GenerationTaskSnapshot
from ..workspace import WorkspaceContext, resolve_workspace
from .problem_info import ProblemInfo, from_job_template


Population = tuple[tuple[float, ...], ...]
Costs = tuple[tuple[float, ...], ...]
WorkspaceLike = WorkspaceContext | str | os.PathLike[str]


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    job_name: str
    x: tuple[float, ...]
    costs: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    generation_index: int
    population: Population
    costs: Costs
    history_count: int
    source: str
    surrogate_used: bool = False
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationContext:
    config: LoadedConfig
    generation_index: int
    population_size: int
    random_seed: int
    run_id: str
    optimization_index: int
    session: CampaignSession
    snapshot: GenerationTaskSnapshot
    history: tuple[HistoryRecord, ...]
    problem: ProblemInfo
    strategy_signature: str
    strategy_identity: Mapping[str, object]


@runtime_checkable
class OptimizationStrategy(Protocol):
    def validate(self, config: LoadedConfig, problem: ProblemInfo) -> None: ...

    def semantic_identity(
        self,
        config: LoadedConfig,
        problem: ProblemInfo,
    ) -> Mapping[str, object]: ...

    def run_generation(self, context: GenerationContext) -> OptimizationResult: ...


@dataclass(frozen=True, slots=True)
class OptimizationDefinition:
    strategy: OptimizationStrategy
    identity: Mapping[str, object]
    signature: str
    source_path: Path


def load_workspace_strategy(
    workspace: WorkspaceLike,
    *,
    config: LoadedConfig | None = None,
    problem: ProblemInfo | None = None,
) -> OptimizationDefinition:
    """Load and validate the one strategy built by ``submit/optimization.py``."""

    context = resolve_workspace(workspace)
    selected_config = load_config(context) if config is None else config
    selected_problem = from_job_template(context) if problem is None else problem
    source_path = context.submit_dir / "optimization.py"
    with task_module(
        context,
        "optimization",
        source_root=context.submit_dir,
    ) as module:
        build = getattr(module, "build_optimization", None)
        if not callable(build) or getattr(build, "__module__", None) != module.__name__:
            raise TypeError(
                f"{source_path} must define callable build_optimization()"
            )
        strategy = build()
    if not isinstance(strategy, OptimizationStrategy):
        raise TypeError(
            f"{source_path} build_optimization() must return a yadof optimization "
            "strategy with validate(), semantic_identity(), and run_generation()"
        )
    strategy.validate(selected_config, selected_problem)
    identity = _json_mapping(
        strategy.semantic_identity(selected_config, selected_problem),
        label=f"{source_path} strategy identity",
    )
    signature = semantic_strategy_signature(
        identity,
        parameter_names=job_template_api.get_parameter_names(context),
        objective_names=selected_problem.objective_names,
    )
    return OptimizationDefinition(
        strategy=strategy,
        identity=identity,
        signature=signature,
        source_path=source_path,
    )


def semantic_strategy_signature(
    identity: Mapping[str, object],
    *,
    parameter_names: Sequence[str],
    objective_names: Sequence[str],
) -> str:
    payload = {
        "strategy": _json_mapping(identity, label="strategy identity"),
        "parameter_names": [str(name) for name in parameter_names],
        "objective_names": [str(name) for name in objective_names],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def history_records(
    workspace: WorkspaceContext,
    *,
    session: CampaignSession | None = None,
    snapshot: GenerationTaskSnapshot | None = None,
) -> tuple[HistoryRecord, ...]:
    try:
        raw_records = (
            session.historical_results(snapshot)
            if session is not None and snapshot is not None
            else recorded_api.get_historical_results(workspace)
        )
    except Exception:
        return ()
    records: list[HistoryRecord] = []
    for item in raw_records or ():
        if isinstance(item, dict):
            name = str(item.get("job_name", item.get("name", "")))
            variables = item.get("normalized_variables", item.get("variables", ()))
            costs = item.get("costs", ())
        else:
            name, variables, costs = item
        records.append(
            HistoryRecord(
                job_name=str(name),
                x=tuple(_clip01(value) for value in variables),
                costs=tuple(float(value) for value in costs),
            )
        )
    return tuple(records)


def resolve_problem_info(
    workspace: WorkspaceContext,
    variable_count: int | None,
    history: Sequence[HistoryRecord],
) -> ProblemInfo:
    history_width = next((len(row.x) for row in history if row.x), None)
    count_hint = history_width if variable_count is None else int(variable_count)
    try:
        return from_job_template(workspace, count_hint)
    except Exception:
        if count_hint is None:
            count_hint = int(job_template_api.get_variable_count(workspace))
        objective_count = next(
            (len(row.costs) for row in history if row.costs),
            1,
        )
        return ProblemInfo(
            variable_count=int(count_hint),
            objective_count=int(objective_count),
            objective_names=tuple(
                f"cost_{index}" for index in range(int(objective_count))
            ),
        )


def evaluate_population(
    context: GenerationContext,
    population: Population,
    *,
    after_jobs_submitted: Callable[[], object] | None = None,
) -> Costs:
    callback_ran = False

    def wrapped_after_jobs_submitted():
        nonlocal callback_ran
        callback_ran = True
        if after_jobs_submitted is not None:
            return after_jobs_submitted()
        return None

    raw_costs = evaluate_api.evaluate_population(
        context.config.workspace,
        population,
        mode=str(context.config.EVALUATION_MODE),
        run_id=context.run_id,
        optimization_index=context.optimization_index,
        generation_index=context.generation_index,
        after_jobs_submitted=(
            wrapped_after_jobs_submitted
            if after_jobs_submitted is not None
            else None
        ),
        _campaign_session=context.session,
        _task_snapshot=context.snapshot,
    )
    if after_jobs_submitted is not None and not callback_ran:
        after_jobs_submitted()
    return tuple(tuple(float(value) for value in row) for row in raw_costs)


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _json_mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    output = {str(key): item for key, item in value.items()}
    try:
        json.dumps(output, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must contain deterministic JSON values: {exc}") from exc
    return output


__all__ = [
    "Costs",
    "GenerationContext",
    "HistoryRecord",
    "OptimizationDefinition",
    "OptimizationResult",
    "OptimizationStrategy",
    "Population",
    "evaluate_population",
    "history_records",
    "load_workspace_strategy",
    "resolve_problem_info",
    "semantic_strategy_signature",
]
