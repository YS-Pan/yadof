from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import inspect
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import (
    DEFAULT_JOB_TEMPLATE_DIR,
    default_jobs_dir,
    default_mode,
    default_timeout_sec,
    local_evaluation_max_workers,
)
from .condor_runner import run_condor_jobs
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
    local_max_workers: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Evaluate a generation and return dynamically computed costs.

    Jobs never calculate or persist cost. Finished, failed, and timed-out jobs
    are written through recorded_data.api; any returned costs are passed back to
    the optimizer as in-memory values only.
    """

    mode = (default_mode() if mode is None else mode).strip().lower()
    jobs_dir = default_jobs_dir() if jobs_dir is None else jobs_dir
    timeout_sec = default_timeout_sec() if timeout_sec is None else timeout_sec

    if mode == "local":
        local_workers = (
            local_evaluation_max_workers()
            if local_max_workers is None
            else max(1, int(local_max_workers))
        )
        return _evaluate_population_local(
            population,
            jobs_dir=jobs_dir,
            job_template_dir=job_template_dir,
            timeout_sec=timeout_sec,
            python_executable=python_executable,
            env=env,
            local_max_workers=local_workers,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            after_jobs_submitted=after_jobs_submitted,
        )
    if mode == "distributed":
        return _evaluate_population_distributed(
            population,
            jobs_dir=jobs_dir,
            job_template_dir=job_template_dir,
            timeout_sec=timeout_sec,
            env=env,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            after_jobs_submitted=after_jobs_submitted,
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
    local_max_workers: int,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    after_jobs_submitted: Callable[[], object] | None,
) -> tuple[tuple[float, ...], ...]:
    jobs_dir = Path(jobs_dir)
    population_rows = tuple(_population_row(variables) for variables in population)
    costs_by_individual: list[tuple[float, ...] | None] = [None] * len(population_rows)
    objective_width: int | None = None

    def evaluate_one(index: int, population_row: tuple[Any, ...]) -> tuple[int, tuple[float, ...] | None]:
        return _evaluate_one_local(
            index=index,
            population_row=population_row,
            jobs_dir=jobs_dir,
            job_template_dir=job_template_dir,
            timeout_sec=timeout_sec,
            python_executable=python_executable,
            env=env,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )

    outcomes: list[tuple[int, tuple[float, ...] | None]] = []
    worker_count = min(max(1, int(local_max_workers)), max(1, len(population_rows)))
    if worker_count <= 1 or len(population_rows) <= 1:
        outcomes = [evaluate_one(index, row) for index, row in enumerate(population_rows)]
    else:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="yadof-local-eval") as executor:
            futures = {
                executor.submit(evaluate_one, index, row): (index, row)
                for index, row in enumerate(population_rows)
            }
            for future in as_completed(futures):
                index, row = futures[future]
                try:
                    outcomes.append(future.result())
                except Exception as exc:  # noqa: BLE001 - keep one worker failure from stopping a generation.
                    failure = _failed_result(
                        stage="local_worker",
                        engine="local",
                        exc=exc,
                        population_row=row,
                        index=index,
                        jobs_dir=jobs_dir,
                        job=None,
                        result=None,
                        run_id=run_id,
                        optimization_index=optimization_index,
                        generation_index=generation_index,
                    )
                    _best_effort_record_failure(failure)
                    outcomes.append((index, None))

    for index, costs in outcomes:
        if costs is None:
            continue

        objective_width = len(costs)
        costs_by_individual[index] = costs

    costs = tuple(costs if costs is not None else _inf_costs(objective_width) for costs in costs_by_individual)
    _run_after_jobs_submitted(after_jobs_submitted)
    return costs


def _evaluate_one_local(
    *,
    index: int,
    population_row: tuple[Any, ...],
    jobs_dir: Path,
    job_template_dir: str | Path,
    timeout_sec: float,
    python_executable: str | Path,
    env: Mapping[str, str] | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
) -> tuple[int, tuple[float, ...] | None]:
    job: JobSpec | None = None
    result: JobResult | None = None

    try:
        job = _prepare_job(
            population_row,
            jobs_dir=jobs_dir,
            job_template_dir=job_template_dir,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            population_index=index,
        )
    except Exception as exc:  # noqa: BLE001 - isolate one failed individual.
        failure = _failed_result(
            stage="prepare",
            engine="local",
            exc=exc,
            population_row=population_row,
            index=index,
            jobs_dir=jobs_dir,
            job=job,
            result=result,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_record_failure(failure)
        return index, None

    try:
        result = run_local_job(job, timeout_sec=timeout_sec, python_executable=python_executable, env=env)
    except Exception as exc:  # noqa: BLE001 - isolate one failed individual.
        failure = _failed_result(
            stage="run",
            engine="local",
            exc=exc,
            population_row=population_row,
            index=index,
            jobs_dir=jobs_dir,
            job=job,
            result=result,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_record_failure(failure)
        return index, None

    try:
        costs = _finalize_result(result)
    except Exception as exc:  # noqa: BLE001 - isolate recorded_data failures.
        failure = _failed_result(
            stage="record",
            engine="local",
            exc=exc,
            population_row=population_row,
            index=index,
            jobs_dir=jobs_dir,
            job=job,
            result=result,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_record_failure(failure)
        return index, None

    return index, costs


def _evaluate_population_distributed(
    population: Iterable[Iterable[float]],
    *,
    jobs_dir: str | Path,
    job_template_dir: str | Path,
    timeout_sec: float,
    env: Mapping[str, str] | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    after_jobs_submitted: Callable[[], object] | None,
) -> tuple[tuple[float, ...], ...]:
    jobs_dir = Path(jobs_dir)
    costs_by_individual: list[tuple[float, ...] | None] = []
    objective_width: int | None = None
    prepared_jobs: list[JobSpec] = []
    prepared_positions: list[int] = []
    population_rows: list[tuple[Any, ...]] = []
    population_items = tuple(population)

    _progress(f"distributed: preparing {len(population_items)} jobs in {jobs_dir}")

    for index, variables in enumerate(population_items):
        population_row = _population_row(variables)
        population_rows.append(population_row)
        costs_by_individual.append(None)
        try:
            job = _prepare_job(
                population_row,
                jobs_dir=jobs_dir,
                job_template_dir=job_template_dir,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
                population_index=index,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one failed individual.
            failure = _failed_result(
                stage="prepare",
                engine="htcondor",
                exc=exc,
                population_row=population_row,
                index=index,
                jobs_dir=jobs_dir,
                job=None,
                result=None,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
            )
            _best_effort_record_failure(failure)
            continue
        prepared_positions.append(index)
        prepared_jobs.append(job)
        if len(prepared_jobs) == 1 or len(prepared_jobs) % 25 == 0 or len(prepared_jobs) == len(population_items):
            _progress(f"distributed: prepared {len(prepared_jobs)}/{len(population_items)} jobs")

    if prepared_jobs:
        _progress(f"distributed: submitting {len(prepared_jobs)} prepared jobs")
        try:
            if after_jobs_submitted is None:
                results = run_condor_jobs(tuple(prepared_jobs), timeout_sec=timeout_sec, env=env)
            else:
                results = run_condor_jobs(
                    tuple(prepared_jobs),
                    timeout_sec=timeout_sec,
                    env=env,
                    after_jobs_submitted=after_jobs_submitted,
                )
        except Exception as exc:  # noqa: BLE001 - backend-wide unexpected failure.
            results = tuple(
                _failed_result(
                    stage="run",
                    engine="htcondor",
                    exc=exc,
                    population_row=population_rows[position],
                    index=position,
                    jobs_dir=jobs_dir,
                    job=job,
                    result=None,
                    run_id=run_id,
                    optimization_index=optimization_index,
                    generation_index=generation_index,
                )
                for position, job in zip(prepared_positions, prepared_jobs)
            )

        for position, job, result in zip(prepared_positions, prepared_jobs, results):
            try:
                costs = _finalize_result(result)
            except Exception as exc:  # noqa: BLE001 - isolate recorded_data failures.
                failure = _failed_result(
                    stage="record",
                    engine="htcondor",
                    exc=exc,
                    population_row=population_rows[position],
                    index=position,
                    jobs_dir=jobs_dir,
                    job=job,
                    result=result,
                    run_id=run_id,
                    optimization_index=optimization_index,
                    generation_index=generation_index,
                )
                _best_effort_record_failure(failure)
                continue

            if costs is None:
                continue
            objective_width = len(costs)
            costs_by_individual[position] = costs
    else:
        _progress("distributed: no jobs were prepared")

    costs = tuple(costs if costs is not None else _inf_costs(objective_width) for costs in costs_by_individual)
    return costs


def _run_after_jobs_submitted(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        callback()
    except Exception as exc:  # noqa: BLE001 - training callbacks must not turn submitted jobs into failures.
        _progress(f"after-submit callback failed: {exc.__class__.__name__}: {exc}")

def _finalize_result(result: JobResult) -> tuple[float, ...] | None:
    costs = record_result(result)
    if result.status != "done":
        return None
    if costs is None:
        raise RuntimeError(
            "recorded_data.api accepted the job result but did not return costs and has no supported job-cost API."
        )
    return tuple(float(x) for x in costs)


def _prepare_job(
    variables: tuple[Any, ...],
    *,
    jobs_dir: Path,
    job_template_dir: str | Path,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    population_index: int,
) -> JobSpec:
    kwargs: dict[str, Any] = {
        "jobs_dir": jobs_dir,
        "job_template_dir": job_template_dir,
        "run_id": run_id,
        "optimization_index": optimization_index,
        "generation_index": generation_index,
        "population_index": population_index,
    }
    try:
        signature = inspect.signature(prepare_job)
    except (TypeError, ValueError):
        return prepare_job(variables, **kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return prepare_job(variables, **kwargs)
    filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return prepare_job(variables, **filtered)


def _best_effort_record_failure(result: JobResult) -> None:
    try:
        record_result(result)
    except Exception:
        return


def _failed_result(
    *,
    stage: str,
    engine: str,
    exc: BaseException,
    population_row: tuple[Any, ...],
    index: int,
    jobs_dir: Path,
    job: JobSpec | None,
    result: JobResult | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
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
            "engine": engine,
            "failure_stage": stage,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "failed_at": now,
            "population_index": index,
            "population_row": _metadata_row(population_row),
        }
    )
    if run_id is not None:
        metadata.setdefault("run_id", str(run_id))
    if optimization_index is not None:
        metadata.setdefault("optimization_index", int(optimization_index))
    if generation_index is not None:
        metadata.setdefault("generation_index", int(generation_index))
    if job is not None and job.population_index is not None:
        metadata.setdefault("population_index", int(job.population_index))
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


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)
