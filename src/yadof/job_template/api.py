"""Workspace-explicit public API for task definitions and dynamic costs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Callable, Iterator, Sequence
import uuid

from ..task_loader import task_module
from ..workspace import WorkspaceContext, resolve_workspace
from .cost_misc import RawVariables, calculate_costs as _calculate_costs
from .parameters_constraints_class import (
    Parameter,
    denormalize_values,
    normalize_values,
)
from .rawdata_contract import RawDataItem


WorkspaceLike = WorkspaceContext | str | os.PathLike[str]
PARAMETERS_FILE_NAME = "parameters_constraints.py"
FAST_EVALUATION_MODULE_NAME = "evaluation"


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    """Validated, immutable summary of one workspace's current task."""

    parameter_names: tuple[str, ...]
    objective_names: tuple[str, ...]
    constraints: tuple[str, ...]

    @property
    def variable_count(self) -> int:
        return len(self.parameter_names)

    @property
    def objective_count(self) -> int:
        return len(self.objective_names)


@dataclass(frozen=True, slots=True)
class CostInterpreter:
    """One frozen parameter and cost-definition view of a workspace task."""

    parameters: tuple[Parameter, ...]
    objective_names: tuple[str, ...]
    _source_path: Path
    _calculate_sample: Callable[
        [Sequence[RawDataItem], RawVariables | None], Sequence[float]
    ]

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(parameter.name for parameter in self.parameters)

    def normalize_variables(
        self, raw_variables: Sequence[float]
    ) -> tuple[float, ...]:
        """Normalize one recorded vector under the frozen parameters."""

        return normalize_values(self.parameters, raw_variables)

    def calculate_costs(
        self,
        samples: Sequence[Sequence[RawDataItem]],
        raw_variables: Sequence[RawVariables | None] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Calculate one batch with the frozen ``calc_cost.py`` callback."""

        rows = _calculate_costs(samples, self._calculate_sample, raw_variables)
        for row in rows:
            if len(row) != len(self.objective_names):
                raise ValueError(
                    f"{self._source_path} returned {len(row)} costs; expected "
                    f"{len(self.objective_names)}"
                )
        return rows


def _workspace(workspace: WorkspaceLike) -> WorkspaceContext:
    return resolve_workspace(workspace)


def _coerce_loaded_parameter(value: object, source_path: Path) -> Parameter:
    required = ("name", "ranges", "value", "normalized_value", "unit")
    missing = tuple(name for name in required if not hasattr(value, name))
    if missing:
        raise TypeError(
            f"{source_path} parameter is missing current fields: {', '.join(missing)}"
        )
    return Parameter(
        getattr(value, "name"),
        getattr(value, "ranges"),
        value=getattr(value, "value"),
        normalized_value=getattr(value, "normalized_value"),
        unit=getattr(value, "unit"),
    )


def _parameter_payload(
    workspace: WorkspaceLike,
) -> tuple[tuple[Parameter, ...], tuple[str, ...]]:
    context = _workspace(workspace)
    source_path = context.job_template_dir / PARAMETERS_FILE_NAME
    with task_module(context, "parameters_constraints") as module:
        if not hasattr(module, "PARAMETERS"):
            raise ValueError(f"{source_path} does not define PARAMETERS")
        if not hasattr(module, "CONSTRAINTS"):
            raise ValueError(f"{source_path} does not define CONSTRAINTS")
        parameters = tuple(
            _coerce_loaded_parameter(item, source_path) for item in module.PARAMETERS
        )
        if isinstance(module.CONSTRAINTS, (str, bytes)):
            raise TypeError(f"{source_path} CONSTRAINTS must be a sequence of strings")
        constraints = tuple(module.CONSTRAINTS)
    if not parameters:
        raise ValueError(f"{source_path} PARAMETERS must not be empty")
    names = tuple(parameter.name for parameter in parameters)
    if any(not name for name in names):
        raise ValueError(f"{source_path} parameter names must not be empty")
    if len(set(names)) != len(names):
        raise ValueError(f"{source_path} parameter names must be unique")
    if not all(isinstance(constraint, str) for constraint in constraints):
        raise TypeError(f"{source_path} CONSTRAINTS must contain only strings")
    return parameters, constraints


def get_parameter_definitions(workspace: WorkspaceLike) -> tuple[Parameter, ...]:
    parameters, _constraints = _parameter_payload(workspace)
    return parameters


def get_constraints(workspace: WorkspaceLike) -> tuple[str, ...]:
    _parameters, constraints = _parameter_payload(workspace)
    return constraints


def get_parameter_metadata(workspace: WorkspaceLike) -> tuple[dict[str, object], ...]:
    return tuple(parameter.to_dict() for parameter in get_parameter_definitions(workspace))


def get_parameter_names(workspace: WorkspaceLike) -> tuple[str, ...]:
    return tuple(parameter.name for parameter in get_parameter_definitions(workspace))


def get_variable_count(workspace: WorkspaceLike) -> int:
    return len(get_parameter_definitions(workspace))


def _objective_names_from_module(module: object, source_path: Path) -> tuple[str, ...]:
    get_names = getattr(module, "get_objective_names", None)
    if not callable(get_names):
        raise TypeError(f"{source_path} must define callable get_objective_names()")
    raw_names = get_names()
    if isinstance(raw_names, (str, bytes)):
        raise TypeError(f"{source_path} objective names must be a sequence of strings")
    names = tuple(raw_names)
    if not names or not all(isinstance(name, str) and name for name in names):
        raise ValueError(f"{source_path} objective names must be non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError(f"{source_path} objective names must be unique")
    get_count = getattr(module, "get_objective_count", None)
    if callable(get_count) and int(get_count()) != len(names):
        raise ValueError(
            f"{source_path} get_objective_count() does not match get_objective_names()"
        )
    return names


def get_objective_names(workspace: WorkspaceLike) -> tuple[str, ...]:
    context = _workspace(workspace)
    source_path = context.job_template_dir / "calc_cost.py"
    with task_module(context, "calc_cost") as module:
        return _objective_names_from_module(module, source_path)


def get_objective_count(workspace: WorkspaceLike) -> int:
    return len(get_objective_names(workspace))


def normalize_variables(
    workspace: WorkspaceLike, raw_variables: Sequence[float]
) -> tuple[float, ...]:
    return normalize_values(get_parameter_definitions(workspace), raw_variables)


def denormalize_variables(
    workspace: WorkspaceLike, normalized_variables: Sequence[float]
) -> tuple[float, ...]:
    return denormalize_values(
        get_parameter_definitions(workspace), normalized_variables
    )


def assign_parameters(
    workspace: WorkspaceLike,
    normalized_variables: Sequence[float],
) -> tuple[Parameter, ...]:
    """Create an in-memory assigned snapshot using canonical task semantics."""

    parameters, _constraints = _parameter_payload(workspace)
    normalized_values = tuple(float(value) for value in normalized_variables)
    if len(normalized_values) != len(parameters):
        raise ValueError(
            f"expected {len(parameters)} normalized values, got {len(normalized_values)}"
        )
    assigned: list[Parameter] = []
    for parameter, normalized_value in zip(parameters, normalized_values):
        if not math.isfinite(normalized_value):
            raise ValueError(
                f"parameter {parameter.name!r} normalized_value must be finite"
            )
        task_parameter = Parameter(
            parameter.name,
            parameter.ranges,
            normalized_value=normalized_value,
            unit=parameter.unit,
        )
        task_parameter.denormalize(update=True)
        assigned.append(task_parameter)
    return tuple(assigned)


def _ranges_source(ranges: Sequence[object]) -> str:
    parts = [
        repr(tuple(item)) if isinstance(item, tuple) else repr(item) for item in ranges
    ]
    if len(parts) == 1:
        return f"({parts[0]},)"
    return "(" + ", ".join(parts) + ")"


def _assigned_parameter_file_text(
    parameters: tuple[Parameter, ...], constraints: tuple[str, ...]
) -> str:
    lines = [
        '"""Job-local parameter definition and assigned-value snapshot."""',
        "",
        "from __future__ import annotations",
        "",
        "",
        "class Parameter:",
        '    """Self-contained assigned parameter used on an execute node."""',
        "",
        "    __slots__ = ('name', 'ranges', 'value', 'normalized_value', 'unit')",
        "",
        "    def __init__(self, name, ranges, *, value=None, normalized_value=None, unit=None):",
        "        self.name = str(name)",
        "        self.ranges = tuple(ranges)",
        "        self.value = value",
        "        self.normalized_value = normalized_value",
        "        self.unit = unit",
        "",
        "PARAMETERS = (",
    ]
    for parameter in parameters:
        lines.append(
            "    Parameter("
            f"{parameter.name!r}, {_ranges_source(parameter.ranges)}, "
            f"value={parameter.value!r}, "
            f"normalized_value={parameter.normalized_value!r}, "
            f"unit={parameter.unit!r}),"
        )
    lines.extend([")", "", "CONSTRAINTS = ("])
    lines.extend(f"    {constraint!r}," for constraint in constraints)
    lines.extend(
        [
            ")",
            "",
            "",
            "def get_parameters() -> tuple[Parameter, ...]:",
            "    return tuple(PARAMETERS)",
            "",
        ]
    )
    return "\n".join(lines)


def materialize_job_parameters(
    workspace: WorkspaceLike,
    normalized_variables: Sequence[float],
    *,
    job_dir: str | os.PathLike[str],
) -> tuple[float, ...]:
    """Write an assigned parameter snapshot into an explicit job directory."""

    _parameters, constraints = _parameter_payload(workspace)
    assigned = assign_parameters(workspace, normalized_variables)

    destination = Path(job_dir).resolve() / PARAMETERS_FILE_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".tmp_{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            _assigned_parameter_file_text(assigned, constraints),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return tuple(parameter.value for parameter in assigned)


def validate_fast_task(workspace: WorkspaceLike) -> Path:
    """Require the explicit fast task kernel without running an evaluation."""

    context = _workspace(workspace)
    source_path = context.job_template_dir / f"{FAST_EVALUATION_MODULE_NAME}.py"
    if not source_path.is_file():
        raise FileNotFoundError(
            "fast evaluation requires task kernel "
            f"{source_path} defining evaluate_rawdata(parameters, context)"
        )
    with task_module(context, FAST_EVALUATION_MODULE_NAME) as module:
        evaluate_rawdata = getattr(module, "evaluate_rawdata", None)
        if not callable(evaluate_rawdata):
            raise TypeError(
                f"{source_path} must define callable "
                "evaluate_rawdata(parameters, context)"
            )
    return source_path


def get_parameter_definition_signature(workspace: WorkspaceLike) -> dict[str, object]:
    parameters, constraints = _parameter_payload(workspace)
    return {
        "parameters": tuple(parameter.to_dict() for parameter in parameters),
        "constraints": constraints,
    }


def calculate_cost(
    workspace: WorkspaceLike,
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Derive costs from rawData with the workspace's freshly loaded task code."""

    context = _workspace(workspace)
    source_path = context.job_template_dir / "calc_cost.py"
    with task_module(context, "calc_cost") as module:
        names = _objective_names_from_module(module, source_path)
        calculate_sample = getattr(module, "calculate_cost", None)
        if not callable(calculate_sample):
            raise TypeError(f"{source_path} must define callable calculate_cost()")
        rows = _calculate_costs(samples, calculate_sample, raw_variables)
    for row in rows:
        if len(row) != len(names):
            raise ValueError(
                f"{source_path} returned {len(row)} costs; expected {len(names)}"
            )
    return rows


@contextmanager
def task_cost_interpreter(
    workspace: WorkspaceLike,
) -> Iterator[CostInterpreter]:
    """Freeze parameters and ``calc_cost.py`` for one multi-row interpretation.

    Point-in-time APIs intentionally reload task code on every call.  A history
    view instead holds one coherent task definition for its complete read and
    reuses it across its decoded-record batches.
    """

    context = _workspace(workspace)
    parameters, _constraints = _parameter_payload(context)
    source_path = context.job_template_dir / "calc_cost.py"
    with task_module(context, "calc_cost") as module:
        names = _objective_names_from_module(module, source_path)
        calculate_sample = getattr(module, "calculate_cost", None)
        if not callable(calculate_sample):
            raise TypeError(f"{source_path} must define callable calculate_cost()")
        yield CostInterpreter(
            parameters,
            names,
            source_path,
            calculate_sample,
        )


def calculate_costs_from_raw_data(
    workspace: WorkspaceLike,
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    return calculate_cost(workspace, samples, raw_variables)


def validate_task(workspace: WorkspaceLike) -> TaskDefinition:
    """Load and validate current parameter and cost contracts without running workflow."""

    context = _workspace(workspace)
    workflow_path = context.job_template_dir / "workflow.py"
    if not workflow_path.is_file():
        raise FileNotFoundError(f"task workflow does not exist: {workflow_path}")
    parameters, constraints = _parameter_payload(context)
    objectives = get_objective_names(context)
    source_path = context.job_template_dir / "calc_cost.py"
    with task_module(context, "calc_cost") as module:
        if callable(getattr(module, "rawdata_importance_weights", None)):
            raise TypeError(
                f"{source_path} defines removed rawdata_importance_weights(); "
                "delete that hook because every numeric rawData field now trains "
                "with equal field-level importance"
            )
    return TaskDefinition(
        parameter_names=tuple(parameter.name for parameter in parameters),
        objective_names=objectives,
        constraints=constraints,
    )


__all__ = [
    "CostInterpreter",
    "FAST_EVALUATION_MODULE_NAME",
    "PARAMETERS_FILE_NAME",
    "TaskDefinition",
    "assign_parameters",
    "calculate_cost",
    "calculate_costs_from_raw_data",
    "denormalize_variables",
    "get_constraints",
    "get_objective_count",
    "get_objective_names",
    "get_parameter_definition_signature",
    "get_parameter_definitions",
    "get_parameter_metadata",
    "get_parameter_names",
    "get_variable_count",
    "materialize_job_parameters",
    "normalize_variables",
    "task_cost_interpreter",
    "validate_task",
    "validate_fast_task",
]
