"""Public API for the job template module."""

from __future__ import annotations

import math
import os
import shutil
import sys
import types
import uuid
from pathlib import Path
from typing import Sequence

from .calc_cost import calculate_cost as _calculate_sample_cost
from .calc_cost import rawdata_importance_weights
from .calc_cost import get_objective_count as _get_objective_count
from .calc_cost import get_objective_names as _get_objective_names
from .cost_misc import RawVariables, calculate_costs as _calculate_costs
from .parameters_constraints_class import Parameter, denormalize_values, normalize_values
from .rawdata_contract import RawDataItem


TEMPLATE_DIR = Path(__file__).resolve().parent
PARAMETERS_FILE_NAME = "parameters_constraints.py"
EXCLUDED_FROM_JOB_COPY = {
    "__init__.py",
    "api.py",
    "batch.log",
    "calc_cost.py",
    "cost_misc.py",
    "cluster.id",
    "condor.log",
    "condor_submit.stderr.txt",
    "condor_submit.stdout.txt",
    "cost.json",
    "individual_metadata.json",
    "job.sub",
    "metaData.json",
    "metadata.json",
    "rawData_outputs.zip",
    "rawdata_contract.py",
    "stderr.txt",
    "stdout.txt",
}
EXCLUDED_DIRS_FROM_JOB_COPY = {
    "._appdata",
    "._home",
    "._localappdata",
    "._tmp",
    "__pycache__",
    "_tmp",
    "history",
}


def get_parameter_definitions() -> tuple[Parameter, ...]:
    parameters, _constraints = _load_parameter_file(TEMPLATE_DIR / PARAMETERS_FILE_NAME)
    return parameters


def get_constraints() -> tuple[str, ...]:
    _parameters, constraints = _load_parameter_file(TEMPLATE_DIR / PARAMETERS_FILE_NAME)
    return constraints


def get_parameter_metadata() -> tuple[dict[str, object], ...]:
    return tuple(parameter.to_dict() for parameter in get_parameter_definitions())


def get_parameter_names() -> tuple[str, ...]:
    return tuple(parameter.name for parameter in get_parameter_definitions())


def get_variable_count() -> int:
    return len(get_parameter_definitions())


def get_objective_names() -> tuple[str, ...]:
    return _get_objective_names()


def get_objective_count() -> int:
    return _get_objective_count()


def normalize_variables(raw_variables: Sequence[float]) -> tuple[float, ...]:
    return normalize_values(get_parameter_definitions(), raw_variables)


def denormalize_variables(normalized_variables: Sequence[float]) -> tuple[float, ...]:
    return denormalize_values(get_parameter_definitions(), normalized_variables)


def materialize_job_parameters(
    normalized_variables: Sequence[float],
    *,
    source_dir: str | Path,
    job_dir: str | Path,
) -> tuple[float, ...]:
    """Write one job's assigned parameter snapshot and return its raw values."""

    source_path = Path(source_dir) / PARAMETERS_FILE_NAME
    parameters, constraints = _load_parameter_file(source_path)
    normalized_values = tuple(float(value) for value in normalized_variables)
    if len(normalized_values) != len(parameters):
        raise ValueError(f"expected {len(parameters)} normalized values, got {len(normalized_values)}")

    assigned: list[Parameter] = []
    for parameter, normalized_value in zip(parameters, normalized_values):
        if not math.isfinite(normalized_value):
            raise ValueError(f"parameter {parameter.name!r} normalized_value must be finite")
        job_parameter = Parameter(
            parameter.name,
            parameter.ranges,
            normalized_value=normalized_value,
            unit=parameter.unit,
        )
        job_parameter.denormalize(update=True)
        if not math.isfinite(job_parameter.value):
            raise ValueError(f"parameter {parameter.name!r} assigned value must be finite")
        assigned.append(job_parameter)

    destination = Path(job_dir) / PARAMETERS_FILE_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(destination.name + f".tmp_{uuid.uuid4().hex}")
    try:
        temp_path.write_text(
            _assigned_parameter_file_text(tuple(assigned), constraints),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
    return tuple(parameter.value for parameter in assigned)


def get_parameter_definition_signature(parameter_file: str | Path) -> dict[str, object]:
    """Return the task-definition portion of a parameter file for static hashing."""

    parameters, constraints = _load_parameter_file(parameter_file)
    return {
        "parameters": tuple(parameter.to_dict() for parameter in parameters),
        "constraints": constraints,
    }


def copy_job_files(job_dir: str | Path) -> Path:
    """Copy default runnable job files into ``job_dir``."""

    destination = Path(job_dir)
    destination.mkdir(parents=True, exist_ok=True)

    for source in TEMPLATE_DIR.iterdir():
        if _skip_template_source(source):
            continue
        target = destination / source.name
        if source.name == "rawData":
            target.mkdir(exist_ok=True)
            continue
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)

    (destination / "rawData").mkdir(exist_ok=True)
    return destination


def _skip_template_source(source: Path) -> bool:
    if source.name in EXCLUDED_FROM_JOB_COPY:
        return True
    if source.is_dir() and source.name in EXCLUDED_DIRS_FROM_JOB_COPY:
        return True
    lowered = source.name.lower()
    return lowered.endswith((".aedtresults", ".aedtresult", ".pyaedt", ".lock"))


def _load_parameter_file(path: str | Path) -> tuple[tuple[Parameter, ...], tuple[str, ...]]:
    """Execute a parameter file in a fresh isolated package namespace."""

    parameter_path = Path(path).resolve()
    if not parameter_path.is_file():
        raise FileNotFoundError(f"parameter definition file does not exist: {parameter_path}")

    package_name = f"_yadof_parameter_source_{uuid.uuid4().hex}"
    module_name = f"{package_name}.parameters_constraints"
    class_module_name = f"{package_name}.parameters_constraints_class"
    class_path = parameter_path.with_name("parameters_constraints_class.py")
    if not class_path.is_file():
        raise FileNotFoundError(f"parameter class file does not exist: {class_path}")
    package = types.ModuleType(package_name)
    package.__file__ = str(parameter_path.parent)
    package.__package__ = package_name
    package.__path__ = [str(parameter_path.parent)]
    module = types.ModuleType(module_name)
    module.__file__ = str(parameter_path)
    module.__package__ = package_name
    class_module = types.ModuleType(class_module_name)
    class_module.__file__ = str(class_path)
    class_module.__package__ = package_name
    sys.modules[package_name] = package
    sys.modules[class_module_name] = class_module
    sys.modules[module_name] = module
    try:
        class_code = compile(class_path.read_bytes(), str(class_path), "exec")
        exec(class_code, class_module.__dict__)
        code = compile(parameter_path.read_bytes(), str(parameter_path), "exec")
        exec(code, module.__dict__)
        if "PARAMETERS" not in module.__dict__:
            raise ValueError(f"{parameter_path} does not define PARAMETERS")
        if "CONSTRAINTS" not in module.__dict__:
            raise ValueError(f"{parameter_path} does not define CONSTRAINTS")
        parameters = tuple(_coerce_loaded_parameter(item, parameter_path) for item in module.PARAMETERS)
        if isinstance(module.CONSTRAINTS, (str, bytes)):
            raise TypeError(f"{parameter_path} CONSTRAINTS must be a sequence of strings")
        constraints = tuple(module.CONSTRAINTS)
        if not all(isinstance(constraint, str) for constraint in constraints):
            raise TypeError(f"{parameter_path} CONSTRAINTS must contain only strings")
        return parameters, constraints
    finally:
        prefix = package_name + "."
        for loaded_name in tuple(sys.modules):
            if loaded_name == package_name or loaded_name.startswith(prefix):
                sys.modules.pop(loaded_name, None)


def _coerce_loaded_parameter(value: object, source_path: Path) -> Parameter:
    required = ("name", "ranges", "value", "normalized_value", "unit")
    missing = tuple(name for name in required if not hasattr(value, name))
    if missing:
        raise TypeError(f"{source_path} parameter is missing current fields: {', '.join(missing)}")
    return Parameter(
        getattr(value, "name"),
        getattr(value, "ranges"),
        value=getattr(value, "value"),
        normalized_value=getattr(value, "normalized_value"),
        unit=getattr(value, "unit"),
    )


def _assigned_parameter_file_text(
    parameters: tuple[Parameter, ...],
    constraints: tuple[str, ...],
) -> str:
    lines = [
        '"""Job-local parameter definition and assigned-value snapshot."""',
        "",
        "from __future__ import annotations",
        "",
        "try:",
        "    from .parameters_constraints_class import Parameter",
        "except ImportError:",
        "    from parameters_constraints_class import Parameter",
        "",
        "PARAMETERS = (",
    ]
    for parameter in parameters:
        lines.append(
            "    Parameter("
            f"{parameter.name!r}, {_ranges_source(parameter.ranges)}, "
            f"value={parameter.value!r}, normalized_value={parameter.normalized_value!r}, "
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


def _ranges_source(ranges) -> str:
    parts = [repr(tuple(item)) if isinstance(item, tuple) else repr(item) for item in ranges]
    if len(parts) == 1:
        return f"({parts[0]},)"
    return "(" + ", ".join(parts) + ")"


def calculate_cost(
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    return _calculate_costs(samples, _calculate_sample_cost, raw_variables)


def calculate_costs_from_raw_data(
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    return calculate_cost(samples, raw_variables)


def calc_costs_from_raw_data(
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    return calculate_cost(samples, raw_variables)


def get_rawdata_importance_weights(
    sample_rawdata: Sequence[RawDataItem],
    *,
    floor: float = 0.25,
    boost: float = 2.0,
) -> tuple[dict[str, object], ...]:
    return rawdata_importance_weights(sample_rawdata, floor=floor, boost=boost)


def calculate_rawdata_importance_weights(
    sample_rawdata: Sequence[RawDataItem],
    *,
    floor: float = 0.25,
    boost: float = 2.0,
) -> tuple[dict[str, object], ...]:
    return get_rawdata_importance_weights(sample_rawdata, floor=floor, boost=boost)
