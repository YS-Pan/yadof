"""Public API for the job template module."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from .calc_cost import RawDataItem, calculate_costs
from .parameters_constraints import get_parameters
from .parameters_constraints_class import denormalize_values, normalize_values


TEMPLATE_DIR = Path(__file__).resolve().parent
EXCLUDED_FROM_JOB_COPY = {"api.py", "calc_cost.py", "__init__.py"}


def get_parameter_definitions():
    return get_parameters()


def get_parameter_metadata() -> tuple[dict[str, object], ...]:
    return tuple(parameter.to_dict() for parameter in get_parameters())


def get_parameter_names() -> tuple[str, ...]:
    return tuple(parameter.name for parameter in get_parameters())


def normalize_variables(raw_variables: Sequence[float]) -> tuple[float, ...]:
    return normalize_values(get_parameters(), raw_variables)


def denormalize_variables(normalized_variables: Sequence[float]) -> tuple[float, ...]:
    return denormalize_values(get_parameters(), normalized_variables)


def copy_job_files(job_dir: str | Path) -> Path:
    """Copy runnable job files into ``job_dir`` without copying calc_cost.py."""

    destination = Path(job_dir)
    destination.mkdir(parents=True, exist_ok=True)

    for source in TEMPLATE_DIR.iterdir():
        if source.name in EXCLUDED_FROM_JOB_COPY or source.name == "__pycache__":
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


def calculate_cost(samples: Sequence[Sequence[RawDataItem]]) -> tuple[tuple[float, ...], ...]:
    return calculate_costs(samples)


def calculate_costs_from_raw_data(samples: Sequence[Sequence[RawDataItem]]) -> tuple[tuple[float, ...], ...]:
    return calculate_cost(samples)


def calc_costs_from_raw_data(samples: Sequence[Sequence[RawDataItem]]) -> tuple[tuple[float, ...], ...]:
    return calculate_cost(samples)
