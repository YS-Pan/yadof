from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Mapping

from .config import DEFAULT_JOB_TEMPLATE_DIR, DEFAULT_JOBS_DIR, DEFAULT_TIMEOUT_SEC
from .job_files import prepare_job
from .local_runner import run_local_job
from .recorded_data_client import record_result
from .types import JobResult


def evaluate_population(
    population: Iterable[Iterable[float]],
    *,
    mode: str = "local",
    jobs_dir: str | Path = DEFAULT_JOBS_DIR,
    job_template_dir: str | Path = DEFAULT_JOB_TEMPLATE_DIR,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Evaluate a generation and return dynamically computed costs.

    Jobs never calculate or persist cost. Finished, failed, and timed-out jobs
    are written through recorded_data.api; any returned costs are passed back to
    the optimizer as in-memory values only.
    """

    if mode == "local":
        return _evaluate_population_local(
            population,
            jobs_dir=jobs_dir,
            job_template_dir=job_template_dir,
            timeout_sec=timeout_sec,
            python_executable=python_executable,
            env=env,
        )
    if mode == "distributed":
        raise NotImplementedError(
            "distributed mode is intentionally a stub in this local minimum; "
            "wire HTCondor submission here while reusing job finalization and recorded_data recording."
        )
    raise ValueError(f"Unsupported evaluate_manager mode: {mode!r}")


def evaluate_generation(*args, **kwargs) -> tuple[tuple[float, ...], ...]:
    return evaluate_population(*args, **kwargs)


def evaluate(*args, **kwargs) -> tuple[tuple[float, ...], ...]:
    return evaluate_population(*args, **kwargs)


def _evaluate_population_local(
    population: Iterable[Iterable[float]],
    *,
    jobs_dir: str | Path,
    job_template_dir: str | Path,
    timeout_sec: float,
    python_executable: str | Path,
    env: Mapping[str, str] | None,
) -> tuple[tuple[float, ...], ...]:
    costs_by_individual: list[tuple[float, ...]] = []
    for variables in population:
        job = prepare_job(variables, jobs_dir=jobs_dir, job_template_dir=job_template_dir)
        result = run_local_job(job, timeout_sec=timeout_sec, python_executable=python_executable, env=env)
        costs = _record_and_get_costs(result)
        costs_by_individual.append(costs)
    return tuple(costs_by_individual)


def _record_and_get_costs(result: JobResult) -> tuple[float, ...]:
    costs = record_result(result)
    if costs is None:
        raise RuntimeError(
            "recorded_data.api accepted the job result but did not return costs and has no supported job-cost API."
        )
    return tuple(float(x) for x in costs)
