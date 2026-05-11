from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ProblemInfo:
    variable_count: int
    objective_count: int
    objective_names: tuple[str, ...]


def from_job_template(variable_count: int | None = None) -> ProblemInfo:
    job_template_api = importlib.import_module("project.job_template.api")
    template_variable_count = int(job_template_api.get_variable_count())
    objective_names = tuple(str(name) for name in job_template_api.get_objective_names())
    objective_count = int(job_template_api.get_objective_count())
    if objective_count != len(objective_names):
        raise ValueError("job_template objective count does not match objective names")
    return ProblemInfo(
        variable_count=int(template_variable_count if variable_count is None else variable_count),
        objective_count=objective_count,
        objective_names=objective_names,
    )
