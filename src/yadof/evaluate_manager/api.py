"""Workspace-explicit local and distributed evaluation API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..config import LoadedConfig, load_config
from ..job_template import get_objective_count, get_variable_count
from ..workspace import WorkspaceContext
from .job_files import prepare_job, validate_task_payload
from .job_result import write_metadata
from .local_runner import run_local_job
from .recorded_data_client import record_result
from .types import JobResult, JobSpec


WorkspaceLike = WorkspaceContext | str | os.PathLike[str]


def evaluate_population(
    workspace: WorkspaceLike,
    population: Iterable[Iterable[float]],
    *,
    mode: str | None = None,
    timeout_sec: float | None = None,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
    local_max_workers: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Evaluate a population and return dynamic cost tuples in input order."""

    overrides: dict[str, object] = {}
    if mode is not None:
        overrides["EVALUATION_MODE"] = str(mode).strip().lower()
    if timeout_sec is not None:
        overrides["EVALUATION_TIMEOUT_SEC"] = float(timeout_sec)
    if local_max_workers is not None:
        overrides["LOCAL_EVALUATION_MAX_WORKERS"] = max(1, int(local_max_workers))
    config = load_config(workspace, overrides=overrides)
    selected_mode = str(config.EVALUATION_MODE).strip().lower()
    if selected_mode == "distributed":
        return _dispatch_distributed(
            config,
            population,
            timeout_sec=float(config.EVALUATION_TIMEOUT_SEC),
            env=env,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            after_jobs_submitted=after_jobs_submitted,
        )
    if selected_mode != "local":
        raise ValueError(f"unsupported evaluation mode: {selected_mode!r}")
    return _dispatch_local(
        config,
        population,
        timeout_sec=float(config.EVALUATION_TIMEOUT_SEC),
        python_executable=python_executable,
        env=env,
        local_max_workers=int(config.LOCAL_EVALUATION_MAX_WORKERS),
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        after_jobs_submitted=after_jobs_submitted,
    )


def run_smoke_test(
    workspace: WorkspaceLike,
    *,
    mode: str = "local",
    normalized_variables: Iterable[float] | None = None,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Run exactly one deterministic representative individual with no timeout."""

    config = load_config(
        workspace,
        overrides={"EVALUATION_MODE": str(mode).strip().lower()},
    )
    selected_mode = str(config.EVALUATION_MODE).strip().lower()
    if normalized_variables is None:
        normalized_variables = (0.5,) * get_variable_count(config.workspace)
    row = tuple(float(value) for value in normalized_variables)
    if selected_mode == "distributed":
        return _dispatch_distributed(
            config,
            (row,),
            timeout_sec=None,
            env=env,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=None,
            after_jobs_submitted=None,
        )
    return _dispatch_local(
        config,
        (row,),
        timeout_sec=None,
        python_executable=python_executable,
        env=env,
        local_max_workers=1,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=None,
        after_jobs_submitted=None,
    )


def evaluate_generation(*args: object, **kwargs: object) -> tuple[tuple[float, ...], ...]:
    return evaluate_population(*args, **kwargs)  # type: ignore[arg-type]


def evaluate(*args: object, **kwargs: object) -> tuple[tuple[float, ...], ...]:
    return evaluate_population(*args, **kwargs)  # type: ignore[arg-type]


def _dispatch_local(
    config: LoadedConfig,
    population: Iterable[Iterable[float]],
    *,
    timeout_sec: float | None,
    python_executable: str | Path,
    env: Mapping[str, str] | None,
    local_max_workers: int,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    after_jobs_submitted: Callable[[], object] | None,
) -> tuple[tuple[float, ...], ...]:
    validate_task_payload(config)
    population_rows = tuple(_population_row(variables) for variables in population)
    objective_width = get_objective_count(config.workspace)
    costs_by_individual: list[tuple[float, ...] | None] = [None] * len(population_rows)

    def evaluate_one(
        index: int, population_row: tuple[Any, ...]
    ) -> tuple[int, tuple[float, ...] | None]:
        return _evaluate_one_local(
            config=config,
            index=index,
            population_row=population_row,
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
        outcomes = [
            evaluate_one(index, row) for index, row in enumerate(population_rows)
        ]
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="yadof-local-eval",
        ) as executor:
            futures = {
                executor.submit(evaluate_one, index, row): (index, row)
                for index, row in enumerate(population_rows)
            }
            for future in as_completed(futures):
                index, row = futures[future]
                try:
                    outcomes.append(future.result())
                except Exception as exc:  # noqa: BLE001 - isolate one worker.
                    _progress(
                        "local worker failed for individual "
                        f"{index}: {type(exc).__name__}: {exc}"
                    )
                    outcomes.append((index, None))

    for index, costs in outcomes:
        if costs is not None:
            costs_by_individual[index] = costs
    _run_after_jobs_submitted(after_jobs_submitted)
    return tuple(
        costs if costs is not None else _inf_costs(objective_width)
        for costs in costs_by_individual
    )


def _evaluate_one_local(
    *,
    config: LoadedConfig,
    index: int,
    population_row: tuple[Any, ...],
    timeout_sec: float | None,
    python_executable: str | Path,
    env: Mapping[str, str] | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
) -> tuple[int, tuple[float, ...] | None]:
    job: JobSpec | None = None
    result: JobResult | None = None
    try:
        job = prepare_job(
            config.workspace,
            population_row,
            config=config,
            mode="local",
            timeout_sec=timeout_sec,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            population_index=index,
        )
    except Exception as exc:  # noqa: BLE001 - isolate one candidate.
        failure = _failed_result(
            stage="prepare",
            engine="local",
            exc=exc,
            population_row=population_row,
            index=index,
            jobs_dir=config.workspace.jobs_dir,
            job=job,
            result=result,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_write_failure(failure)
        _best_effort_record_failure(config.workspace, failure)
        return index, None

    try:
        result = run_local_job(
            job,
            timeout_sec=timeout_sec,
            python_executable=python_executable,
            env=env,
        )
    except Exception as exc:  # noqa: BLE001 - isolate one candidate.
        failure = _failed_result(
            stage="run",
            engine="local",
            exc=exc,
            population_row=population_row,
            index=index,
            jobs_dir=config.workspace.jobs_dir,
            job=job,
            result=result,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_write_failure(failure)
        _best_effort_record_failure(config.workspace, failure)
        return index, None

    if result.status != "done":
        _best_effort_record_failure(config.workspace, result)
        return index, None
    try:
        costs = record_result(config.workspace, result)
        if costs is None:
            raise RuntimeError("completed recorded result returned no costs")
    except Exception as exc:  # noqa: BLE001 - recording/cost failure is per individual.
        failure = _failed_result(
            stage="recorded_data",
            engine="local",
            exc=exc,
            population_row=population_row,
            index=index,
            jobs_dir=config.workspace.jobs_dir,
            job=job,
            result=result,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_write_failure(failure)
        return index, None
    return index, tuple(float(value) for value in costs)


def _dispatch_distributed(
    config: LoadedConfig,
    population: Iterable[Iterable[float]],
    *,
    timeout_sec: float | None,
    env: Mapping[str, str] | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    after_jobs_submitted: Callable[[], object] | None,
) -> tuple[tuple[float, ...], ...]:
    from .condor_runner import run_condor_jobs

    validate_task_payload(config)
    rows = tuple(_population_row(values) for values in population)
    objective_width = get_objective_count(config.workspace)
    costs: list[tuple[float, ...] | None] = [None] * len(rows)
    jobs: list[JobSpec] = []
    positions: list[int] = []

    for index, row in enumerate(rows):
        try:
            job = prepare_job(
                config.workspace,
                row,
                config=config,
                mode="distributed",
                timeout_sec=timeout_sec,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
                population_index=index,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one candidate.
            failure = _failed_result(
                stage="prepare",
                engine="htcondor",
                exc=exc,
                population_row=row,
                index=index,
                jobs_dir=config.workspace.jobs_dir,
                job=None,
                result=None,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
            )
            _best_effort_record_failure(config.workspace, failure)
            continue
        jobs.append(job)
        positions.append(index)

    try:
        results = run_condor_jobs(
            config.workspace,
            tuple(jobs),
            config=config,
            timeout_sec=timeout_sec,
            env=env,
            after_jobs_submitted=after_jobs_submitted,
        )
    except Exception as exc:  # noqa: BLE001 - preserve generation shape.
        results = tuple(
            _failed_result(
                stage="run",
                engine="htcondor",
                exc=exc,
                population_row=rows[position],
                index=position,
                jobs_dir=config.workspace.jobs_dir,
                job=job,
                result=None,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
            )
            for position, job in zip(positions, jobs)
        )

    for position, result in zip(positions, results):
        if result.status != "done":
            _best_effort_record_failure(config.workspace, result)
            continue
        try:
            row_costs = record_result(config.workspace, result)
            if row_costs is None:
                raise RuntimeError("completed recorded result returned no costs")
        except Exception as exc:  # noqa: BLE001 - isolate recording failures.
            failure = _failed_result(
                stage="recorded_data",
                engine="htcondor",
                exc=exc,
                population_row=rows[position],
                index=position,
                jobs_dir=config.workspace.jobs_dir,
                job=jobs[positions.index(position)],
                result=result,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
            )
            _best_effort_write_failure(failure)
            continue
        costs[position] = tuple(float(value) for value in row_costs)

    return tuple(
        row if row is not None else _inf_costs(objective_width) for row in costs
    )


def _run_after_jobs_submitted(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        callback()
    except Exception as exc:  # noqa: BLE001 - callbacks do not change job results.
        _progress(f"after-submit callback failed: {type(exc).__name__}: {exc}")


def _best_effort_write_failure(result: JobResult) -> None:
    if not result.job_dir.is_dir():
        return
    try:
        write_metadata(result.job_dir, result.metadata)
    except OSError:
        return


def _best_effort_record_failure(
    workspace: WorkspaceContext, result: JobResult
) -> None:
    try:
        record_result(workspace, result)
    except Exception:  # noqa: BLE001 - recording never stops the remaining population.
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
    job_name = (
        _failure_job_name(index, now)
        if job is None and result is None
        else (result.job_name if result else job.name)
    )
    job_dir = (
        jobs_dir / job_name
        if job is None and result is None
        else (result.job_dir if result else job.directory)
    )
    variables = (
        tuple(float(value) for value in result.unnormalized_variables)
        if result is not None
        else (
            tuple(float(value) for value in job.unnormalized_variables)
            if job is not None
            else ()
        )
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


def _metadata_row(values: Iterable[Any]) -> list[Any]:
    return [
        value
        if isinstance(value, (str, int, float, bool)) or value is None
        else repr(value)
        for value in values
    ]


def _inf_costs(objective_width: int) -> tuple[float, ...]:
    return tuple(math.inf for _ in range(max(1, int(objective_width))))


def _failure_job_name(index: int, timestamp: str) -> str:
    safe_stamp = timestamp.replace(":", "").replace(".", "").replace("+", "_")
    return f"failed_individual_{index}_{safe_stamp}"


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print(f"[yadof] {message}", flush=True)


__all__ = [
    "evaluate",
    "evaluate_generation",
    "evaluate_population",
    "run_smoke_test",
]
