"""Public API for the job template module."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from .calc_cost import RawDataItem, RawVariables, calculate_costs, rawdata_importance_weights
from .calc_cost import get_objective_count as _get_objective_count
from .calc_cost import get_objective_names as _get_objective_names
from .parameters_constraints import get_parameters
from .parameters_constraints_class import denormalize_values, normalize_values


TEMPLATE_DIR = Path(__file__).resolve().parent
EXCLUDED_FROM_JOB_COPY = {
    "__init__.py",
    "api.py",
    "batch.log",
    "calc_cost.py",
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


def get_parameter_definitions():
    return get_parameters()


def get_parameter_metadata() -> tuple[dict[str, object], ...]:
    return tuple(parameter.to_dict() for parameter in get_parameters())


def get_parameter_names() -> tuple[str, ...]:
    return tuple(parameter.name for parameter in get_parameters())


def get_variable_count() -> int:
    return len(get_parameters())


def get_objective_names() -> tuple[str, ...]:
    return _get_objective_names()


def get_objective_count() -> int:
    return _get_objective_count()


def normalize_variables(raw_variables: Sequence[float]) -> tuple[float, ...]:
    return normalize_values(get_parameters(), raw_variables)


def denormalize_variables(normalized_variables: Sequence[float]) -> tuple[float, ...]:
    return denormalize_values(get_parameters(), normalized_variables)


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

def calculate_cost(
    samples: Sequence[Sequence[RawDataItem]],
    raw_variables: Sequence[RawVariables | None] | None = None,
) -> tuple[tuple[float, ...], ...]:
    return calculate_costs(samples, raw_variables)


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
