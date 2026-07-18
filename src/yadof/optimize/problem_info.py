from __future__ import annotations

from dataclasses import dataclass

from ..job_template import api as job_template_api
from ..workspace import WorkspaceContext


@dataclass(frozen=True)
class ProblemInfo:
    variable_count: int
    objective_count: int
    objective_names: tuple[str, ...]


def from_job_template(
    workspace: WorkspaceContext, variable_count: int | None = None
) -> ProblemInfo:
    template_variable_count = int(job_template_api.get_variable_count(workspace))
    objective_names = tuple(
        str(name) for name in job_template_api.get_objective_names(workspace)
    )
    objective_count = int(job_template_api.get_objective_count(workspace))
    if objective_count != len(objective_names):
        raise ValueError("job_template objective count does not match objective names")
    return ProblemInfo(
        variable_count=int(template_variable_count if variable_count is None else variable_count),
        objective_count=objective_count,
        objective_names=objective_names,
    )
