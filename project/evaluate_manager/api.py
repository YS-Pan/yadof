from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .config import DEFAULT_JOB_TEMPLATE_DIR, default_jobs_dir, default_mode, default_timeout_sec
from .job_files import prepare_job
from .local_runner import run_local_job
from .recorded_data_client import record_result
from .types import JobResult, JobSpec


def evaluate_population(
    population: Iterable[Iterable[float]],
    *,
    mode: str | None = None,
    jobs_dir: str | Path | None = None,
    job_template_dir: str | Path = DEFAULT_JOB_TEMPLATE_DIR,
    timeout_sec: float | None = None,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Evaluate a generation and return dynamically computed costs.

    Jobs never calculate or persist cost. Finished, failed, and timed-out jobs
    are written through recorded_data.api; any returned costs are passed back to
    the optimizer as in-memory values only.
    """

    mode = default_mode() if mode is None else mode
    jobs_dir = default_jobs_dir() if jobs_dir is None else jobs_dir
    timeout_sec = default_timeout_sec() if timeout_sec is None else timeout_sec

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
            "distributed evaluate_manager mode is not implemented yet; "
            "local mode uses isolated per-individual finalization."
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
    jobs_dir = Path(jobs_dir)
    costs_by_individual: list[tuple[float, ...] | None] = []
    objective_width: int | None = None

    for index, variables in enumerate(population):
        population_row = _population_row(variables)
        job: JobSpec | None = None
        result: JobResult | None = None

        try:
            job = prepare_job(population_row, jobs_dir=jobs_dir, job_template_dir=job_template_dir)
        except Exception as exc:  # noqa: BLE001 - isolate one failed individual.
            failure = _failed_result(
                stage="prepare",
                exc=exc,
                population_row=population_row,
                index=index,
                jobs_dir=jobs_dir,
                job=job,
                result=result,
            )
            _best_effort_record_failure(failure)
            costs_by_individual.append(None)
            continue

        try:
            result = run_local_job(job, timeout_sec=timeout_sec, python_executable=python_executable, env=env)
        except Exception as exc:  # noqa: BLE001 - isolate one failed individual.
            failure = _failed_result(
                stage="run",
                exc=exc,
                population_row=population_row,
                index=index,
                jobs_dir=jobs_dir,
                job=job,
                result=result,
            )
            _best_effort_record_failure(failure)
            costs_by_individual.append(None)
            continue

        try:
            costs = _finalize_result(result)
        except Exception as exc:  # noqa: BLE001 - isolate recorded_data failures.
            failure = _failed_result(
                stage="record",
                exc=exc,
                population_row=population_row,
                index=index,
                jobs_dir=jobs_dir,
                job=job,
                result=result,
            )
            _best_effort_record_failure(failure)
            costs_by_individual.append(None)
            continue

        if costs is None:
            costs_by_individual.append(None)
            continue

        objective_width = len(costs)
        costs_by_individual.append(costs)

    return tuple(costs if costs is not None else _inf_costs(objective_width) for costs in costs_by_individual)


def _finalize_result(result: JobResult) -> tuple[float, ...] | None:
    costs = record_result(result)
    if result.status != "done":
        return None
    if costs is None:
        raise RuntimeError(
            "recorded_data.api accepted the job result but did not return costs and has no supported job-cost API."
        )
    return tuple(float(x) for x in costs)


def _best_effort_record_failure(result: JobResult) -> None:
    try:
        record_result(result)
    except Exception:
        return


def _failed_result(
    *,
    stage: str,
    exc: BaseException,
    population_row: tuple[Any, ...],
    index: int,
    jobs_dir: Path,
    job: JobSpec | None,
    result: JobResult | None,
) -> JobResult:
    now = _now_text()
    job_name = _failure_job_name(index, now) if job is None and result is None else (result.job_name if result else job.name)
    job_dir = jobs_dir if job is None and result is None else (result.job_dir if result else job.directory)
    variables: tuple[float, ...] = (
        tuple(float(x) for x in result.unnormalized_variables)
        if result is not None
        else (tuple(float(x) for x in job.unnormalized_variables) if job is not None else _float_tuple(population_row))
    )
    metadata: dict[str, Any] = {}
    if result is not None:
        metadata.update(result.metadata)
    metadata.update(
        {
            "job_name": job_name,
            "status": "error",
            "engine": "local",
            "failure_stage": stage,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "failed_at": now,
            "population_index": index,
            "population_row": _metadata_row(population_row),
        }
    )
    return JobResult(
        job_name=job_name,
        job_dir=Path(job_dir),
        status="error",
        unnormalized_variables=variables,
        raw_data_paths=tuple(result.raw_data_paths) if result is not None else (),
        metadata=metadata,
    )


def _population_row(variables: Iterable[float]) -> tuple[Any, ...]:
    return tuple(variables)


def _float_tuple(values: Iterable[Any]) -> tuple[float, ...]:
    converted: list[float] = []
    for value in values:
        try:
            converted.append(float(value))
        except (TypeError, ValueError):
            continue
    return tuple(converted)


def _metadata_row(values: Iterable[Any]) -> list[Any]:
    row = []
    for value in values:
        if isinstance(value, (str, int, float, bool)) or value is None:
            row.append(value)
        else:
            row.append(repr(value))
    return row


def _inf_costs(objective_width: int | None) -> tuple[float, ...]:
    width = 1 if objective_width is None or objective_width < 1 else objective_width
    return tuple(float("inf") for _ in range(width))


def _failure_job_name(index: int, timestamp: str) -> str:
    safe_stamp = timestamp.replace(":", "").replace(".", "").replace("+", "_")
    return f"failed_individual_{index}_{safe_stamp}"


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
