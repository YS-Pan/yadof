"""Explicit optimization generation values, history, and semantic identity."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, Sequence

from ..config import LoadedConfig
from ..job_template import api as job_template_api
from ..recorded_data import api as recorded_api
from ..recorded_data.session import CampaignSession
from ..task_snapshot import GenerationTaskSnapshot
from ..workspace import WorkspaceContext
from .problem_info import ProblemInfo, from_job_template


Population = tuple[tuple[float, ...], ...]
Costs = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    job_name: str
    x: tuple[float, ...]
    costs: tuple[float, ...]
    candidate_id: str = ""
    row_id: str = ""
    design_key: str | None = None
    interpretation_id: str = ""


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
        if session is not None and snapshot is not None:
            dataset = session.evidence_dataset()
            table = session.cost_table(snapshot)
        else:
            dataset = recorded_api.get_evidence_dataset(workspace)
            table = recorded_api.get_cost_table(workspace, dataset=dataset)
        joined = dataset.join_costs(table)
    except Exception:
        return ()
    records: list[HistoryRecord] = []
    for item in joined:
        evidence = item.evidence
        cost = item.cost
        if (
            not evidence.is_durable
            or evidence.execution_status != "completed"
            or not cost.valid
            or cost.normalized_variables is None
            or cost.costs is None
        ):
            continue
        records.append(
            HistoryRecord(
                job_name=evidence.job_name,
                x=tuple(_clip01(value) for value in cost.normalized_variables),
                costs=tuple(float(value) for value in cost.costs),
                candidate_id=evidence.evidence_id,
                row_id=evidence.row_id,
                design_key=evidence.design_key,
                interpretation_id=cost.interpretation_id,
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
    "OptimizationResult",
    "Population",
    "history_records",
    "resolve_problem_info",
    "semantic_strategy_signature",
]
