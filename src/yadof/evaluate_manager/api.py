"""Workspace-explicit fast, local, and distributed evaluation API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..config import LoadedConfig, load_config
from ..job_template import get_objective_count, get_variable_count, validate_fast_task
from ..workspace import WorkspaceContext
from ..recorded_data.session import CampaignSession, RecordingError
from ..task_snapshot import GenerationTaskSnapshot
from .finalizer import ResultFinalizationCoordinator
from .job_files import prepare_job, validate_task_payload
from .job_result import write_metadata
from .lifecycle import EvaluationBatch, EvaluationHandle
from .local_runner import run_local_job
from .local_resources import plan_local_workers
from .types import EvaluationResult, JobResult, JobSpec


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
    fast_max_workers: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
    _campaign_session: CampaignSession | None = None,
    _task_snapshot: GenerationTaskSnapshot | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Synchronously compose the common prepare/start/wait/close lifecycle."""

    batch = prepare_evaluation(
        workspace,
        population,
        mode=mode,
        timeout_sec=timeout_sec,
        python_executable=python_executable,
        env=env,
        local_max_workers=local_max_workers,
        fast_max_workers=fast_max_workers,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        after_jobs_submitted=after_jobs_submitted,
        _campaign_session=_campaign_session,
        _task_snapshot=_task_snapshot,
    )
    handle = start_evaluation(batch)
    try:
        result = handle.wait()
    except BaseException:
        try:
            handle.close()
        except BaseException:
            pass
        raise
    handle.close()
    return result.costs


def prepare_evaluation(
    workspace: WorkspaceLike,
    population: Iterable[Iterable[float]],
    *,
    mode: str | None = None,
    timeout_sec: float | None = None,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
    local_max_workers: int | None = None,
    fast_max_workers: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
    _campaign_session: CampaignSession | None = None,
    _task_snapshot: GenerationTaskSnapshot | None = None,
) -> EvaluationBatch:
    """Freeze one population/configuration without opening backend resources."""

    return _prepare_evaluation_batch(
        workspace,
        population,
        mode=mode,
        timeout_sec=timeout_sec,
        use_config_timeout=True,
        python_executable=python_executable,
        env=env,
        local_max_workers=local_max_workers,
        fast_max_workers=fast_max_workers,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        after_jobs_submitted=after_jobs_submitted,
        campaign_session=_campaign_session,
        task_snapshot=_task_snapshot,
        phase="evaluation",
    )


def start_evaluation(batch: EvaluationBatch) -> EvaluationHandle:
    """Create and start the backend-neutral owner for one prepared batch."""

    handle = EvaluationHandle(batch)
    try:
        return handle.start()
    except BaseException:
        try:
            handle.close()
        except BaseException:
            pass
        raise


def _prepare_evaluation_batch(
    workspace: WorkspaceLike,
    population: Iterable[Iterable[float]],
    *,
    mode: str | None,
    timeout_sec: float | None,
    use_config_timeout: bool,
    python_executable: str | Path,
    env: Mapping[str, str] | None,
    local_max_workers: int | None,
    fast_max_workers: int | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    after_jobs_submitted: Callable[[], object] | None,
    campaign_session: CampaignSession | None,
    task_snapshot: GenerationTaskSnapshot | None,
    phase: str,
) -> EvaluationBatch:
    rows = tuple(_population_row(values) for values in population)
    overrides: dict[str, object] = {}
    if mode is not None:
        overrides["EVALUATION_MODE"] = str(mode).strip().lower()
    if timeout_sec is not None:
        overrides["EVALUATION_TIMEOUT_SEC"] = float(timeout_sec)
    if local_max_workers is not None:
        overrides["LOCAL_EVALUATION_MAX_WORKERS"] = max(1, int(local_max_workers))
    if fast_max_workers is not None:
        overrides["FAST_EVALUATION_MAX_WORKERS"] = max(1, int(fast_max_workers))
    if campaign_session is None:
        if task_snapshot is not None:
            raise ValueError("task snapshot requires a campaign session")
        config = load_config(workspace, overrides=overrides)
    else:
        if task_snapshot is None:
            raise ValueError("_task_snapshot is required with _campaign_session")
        config = task_snapshot.config
    selected_mode = str(config.EVALUATION_MODE).strip().lower()
    if selected_mode not in {"fast", "local", "distributed"}:
        raise ValueError(f"unsupported evaluation mode: {selected_mode!r}")
    executable = Path(python_executable)
    if selected_mode == "fast" and executable.resolve() != Path(sys.executable).resolve():
        raise ValueError(
            "fast evaluation workers use the current Python executable; "
            "python_executable cannot select another runtime"
        )
    effective_timeout = (
        float(config.EVALUATION_TIMEOUT_SEC)
        if use_config_timeout and timeout_sec is None
        else (None if timeout_sec is None else float(timeout_sec))
    )
    environment = tuple(
        sorted(
            ((str(key), str(value)) for key, value in (env or {}).items()),
            key=lambda item: item[0],
        )
    )
    return EvaluationBatch(
        workspace=config.workspace,
        population=rows,
        config=config,
        mode=selected_mode,
        timeout_sec=effective_timeout,
        python_executable=executable,
        environment=environment,
        local_max_workers=int(config.LOCAL_EVALUATION_MAX_WORKERS),
        fast_max_workers=int(config.FAST_EVALUATION_MAX_WORKERS),
        objective_width=get_objective_count(config.workspace),
        run_id=None if run_id is None else str(run_id),
        optimization_index=(
            None if optimization_index is None else int(optimization_index)
        ),
        generation_index=None if generation_index is None else int(generation_index),
        phase=phase,
        _campaign_session=campaign_session,
        _task_snapshot=task_snapshot,
        _after_jobs_submitted=after_jobs_submitted,
    )


def _execute_evaluation_batch(
    batch: EvaluationBatch,
    cancel_event: threading.Event,
) -> EvaluationResult:
    """Run one handle-owned backend lifecycle and expose only finalized rows."""

    owns_session = batch._campaign_session is None
    if owns_session:
        session = CampaignSession(batch.config)
        try:
            snapshot = session.begin_generation(batch.config)
        except BaseException:
            session.close()
            raise
    else:
        session = batch._campaign_session
        snapshot = batch._task_snapshot
        if session is None or snapshot is None:
            raise RuntimeError("prepared campaign batch lost its session snapshot")
    config = snapshot.config
    progress = _PopulationProgress(
        total=len(batch.population),
        mode=batch.mode,
        generation_index=batch.generation_index,
        phase=batch.phase,
    )
    progress.start()
    started = time.monotonic()
    try:
        if batch.mode == "fast":
            rows = _dispatch_fast(
                config,
                batch.population,
                timeout_sec=batch.timeout_sec,
                env=batch.env,
                fast_max_workers=batch.fast_max_workers,
                run_id=batch.run_id,
                optimization_index=batch.optimization_index,
                generation_index=batch.generation_index,
                progress=progress,
                session=session,
                snapshot=snapshot,
                cancel_event=cancel_event,
            )
        elif batch.mode == "distributed":
            rows = _dispatch_distributed(
                config,
                batch.population,
                timeout_sec=batch.timeout_sec,
                env=batch.env,
                run_id=batch.run_id,
                optimization_index=batch.optimization_index,
                generation_index=batch.generation_index,
                after_jobs_submitted=batch._after_jobs_submitted,
                progress=progress,
                session=session,
                snapshot=snapshot,
                cancel_event=cancel_event,
            )
        else:
            rows = _dispatch_local(
                config,
                batch.population,
                timeout_sec=batch.timeout_sec,
                python_executable=batch.python_executable,
                env=batch.env,
                local_max_workers=batch.local_max_workers,
                run_id=batch.run_id,
                optimization_index=batch.optimization_index,
                generation_index=batch.generation_index,
                after_jobs_submitted=batch._after_jobs_submitted,
                progress=progress,
                session=session,
                snapshot=snapshot,
                cancel_event=cancel_event,
            )
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row.status] = status_counts.get(row.status, 0) + 1
        return EvaluationResult(
            batch_id=batch.batch_id,
            mode=batch.mode,
            rows=rows,
            objective_width=batch.objective_width,
            cancel_requested=cancel_event.is_set(),
            diagnostics={
                "candidate_count": len(rows),
                "status_counts": status_counts,
                "elapsed_sec": max(0.0, time.monotonic() - started),
                "generation_index": batch.generation_index,
            },
        )
    finally:
        progress.close()
        if owns_session:
            session.close()


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
    """Run one deterministic representative through the common handle lifecycle."""

    if normalized_variables is None:
        normalized_variables = (0.5,) * get_variable_count(workspace)
    row = tuple(float(value) for value in normalized_variables)
    batch = _prepare_evaluation_batch(
        workspace,
        (row,),
        mode=mode,
        timeout_sec=None,
        use_config_timeout=False,
        python_executable=python_executable,
        env=env,
        local_max_workers=1,
        fast_max_workers=1,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=None,
        after_jobs_submitted=None,
        campaign_session=None,
        task_snapshot=None,
        phase="smoke",
    )
    handle = start_evaluation(batch)
    try:
        result = handle.wait()
    except BaseException:
        try:
            handle.close()
        except BaseException:
            pass
        raise
    handle.close()
    return result.costs


def evaluate_generation(*args: object, **kwargs: object) -> tuple[tuple[float, ...], ...]:
    return evaluate_population(*args, **kwargs)  # type: ignore[arg-type]


def evaluate(*args: object, **kwargs: object) -> tuple[tuple[float, ...], ...]:
    return evaluate_population(*args, **kwargs)  # type: ignore[arg-type]


def _dispatch_fast(
    config: LoadedConfig,
    population: Iterable[Iterable[float]],
    *,
    timeout_sec: float | None,
    env: Mapping[str, str] | None,
    fast_max_workers: int,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    progress: _PopulationProgress,
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    cancel_event: threading.Event,
) -> tuple[JobResult, ...]:
    from .fast_runner import run_fast_population

    validate_fast_task(config.workspace)
    rows = tuple(population)

    def expose(index: int, finalized: JobResult) -> None:
        progress.complete(index, successful=finalized.costs is not None)

    coordinator = ResultFinalizationCoordinator(
        session,
        snapshot,
        expected_count=len(rows),
        on_finalized=expose,
    )
    try:
        run_fast_population(
            config,
            rows,
            timeout_sec=timeout_sec,
            env=env,
            max_workers=fast_max_workers,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            on_result=coordinator.accept,
            cancel_event=cancel_event,
        )
        finalized = coordinator.finish()
    except BaseException:
        coordinator.close()
        raise
    return finalized


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
    progress: _PopulationProgress,
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    cancel_event: threading.Event,
) -> tuple[JobResult, ...]:
    validate_task_payload(config)
    population_rows = tuple(population)
    worker_plan = plan_local_workers(
        config,
        population_size=len(population_rows),
        configured_max=local_max_workers,
        generation_index=generation_index,
        run_id=run_id,
        history_records=session.records(),
    )
    worker_plan_metadata = worker_plan.metadata()
    _progress(worker_plan.summary())

    def expose(index: int, finalized: JobResult) -> None:
        progress.complete(index, successful=finalized.costs is not None)

    coordinator = ResultFinalizationCoordinator(
        session,
        snapshot,
        expected_count=len(population_rows),
        on_finalized=expose,
    )

    def evaluate_one(
        index: int, population_row: tuple[Any, ...]
    ) -> tuple[int, JobResult]:
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
            worker_plan_metadata=worker_plan_metadata,
            cancel_event=cancel_event,
        )

    try:
        worker_count = worker_plan.worker_count
        if worker_count <= 1 or len(population_rows) <= 1:
            for index, row in enumerate(population_rows):
                outcome = evaluate_one(index, row)
                coordinator.accept(index, outcome[1])
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
                        outcome = future.result()
                    except Exception as exc:  # noqa: BLE001 - isolate one worker.
                        _progress(
                            "local worker failed for individual "
                            f"{index}: {type(exc).__name__}: {exc}"
                        )
                        outcome = (
                            index,
                            _failed_result(
                                stage="local_worker",
                                engine="local",
                                exc=exc,
                                population_row=row,
                                index=index,
                                jobs_dir=config.workspace.jobs_dir,
                                job=None,
                                result=None,
                                run_id=run_id,
                                optimization_index=optimization_index,
                                generation_index=generation_index,
                            ),
                        )
                    coordinator.accept(index, outcome[1])
        finalized = coordinator.finish()
    except BaseException:
        coordinator.close()
        raise
    _run_after_jobs_submitted(after_jobs_submitted)
    return finalized


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
    worker_plan_metadata: Mapping[str, object],
    cancel_event: threading.Event,
) -> tuple[int, JobResult]:
    job: JobSpec | None = None
    result: JobResult | None = None
    if cancel_event.is_set():
        return index, _cancelled_result(
            stage="before_prepare",
            engine="local",
            population_row=population_row,
            index=index,
            jobs_dir=config.workspace.jobs_dir,
            job=None,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
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
        return index, failure

    if cancel_event.is_set():
        cancelled = _cancelled_result(
            stage="before_run",
            engine="local",
            population_row=population_row,
            index=index,
            jobs_dir=config.workspace.jobs_dir,
            job=job,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
        )
        _best_effort_write_failure(cancelled)
        return index, cancelled

    try:
        result = run_local_job(
            job,
            timeout_sec=timeout_sec,
            python_executable=python_executable,
            env=env,
            plan_metadata=worker_plan_metadata,
            cancel_event=cancel_event,
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
        return index, failure

    return index, result


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
    progress: _PopulationProgress,
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    cancel_event: threading.Event,
) -> tuple[JobResult, ...]:
    from .condor_runner import run_condor_jobs

    validate_task_payload(config)
    rows = tuple(population)
    jobs: list[JobSpec] = []
    positions: list[int] = []

    def expose(index: int, finalized: JobResult) -> None:
        progress.complete(index, successful=finalized.costs is not None)

    coordinator = ResultFinalizationCoordinator(
        session,
        snapshot,
        expected_count=len(rows),
        on_finalized=expose,
    )
    accepted_positions: set[int] = set()

    for index, row in enumerate(rows):
        if cancel_event.is_set():
            coordinator.accept(
                index,
                _cancelled_result(
                    stage="before_prepare",
                    engine="htcondor",
                    population_row=row,
                    index=index,
                    jobs_dir=config.workspace.jobs_dir,
                    job=None,
                    run_id=run_id,
                    optimization_index=optimization_index,
                    generation_index=generation_index,
                ),
            )
            accepted_positions.add(index)
            continue
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
            coordinator.accept(index, failure)
            accepted_positions.add(index)
            continue
        jobs.append(job)
        positions.append(index)

    positions_by_job = {
        job.name: position for position, job in zip(positions, jobs)
    }

    def consume_result(result: JobResult) -> None:
        position = positions_by_job.get(result.job_name)
        if position is None or position in accepted_positions:
            return
        coordinator.accept(position, result)
        accepted_positions.add(position)

    try:
        results = run_condor_jobs(
            config.workspace,
            tuple(jobs),
            config=config,
            timeout_sec=timeout_sec,
            env=env,
            after_jobs_submitted=after_jobs_submitted,
            on_result=consume_result,
            history_records=session.records(),
            cancel_event=cancel_event,
        )
    except RecordingError:
        coordinator.close()
        raise
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
        if position in accepted_positions:
            continue
        coordinator.accept(position, result)
        accepted_positions.add(position)
    try:
        finalized = coordinator.finish()
    except BaseException:
        coordinator.close()
        raise
    return finalized


def _run_after_jobs_submitted(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        callback()
    except Exception as exc:  # noqa: BLE001 - callbacks do not change job results.
        _progress(f"after-submit callback failed: {type(exc).__name__}: {exc}")


def _best_effort_write_failure(result: JobResult) -> None:
    if result.job_dir is None or not result.job_dir.is_dir():
        return
    try:
        write_metadata(result.job_dir, result.metadata)
    except OSError:
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
        job_dir=Path(job_dir) if job_dir is not None else None,
        status="error",
        unnormalized_variables=variables,
        normalized_variables=(
            tuple(result.normalized_variables)
            if result is not None
            else tuple(float(value) for value in population_row)
        ),
        raw_data_paths=tuple(result.raw_data_paths) if result is not None else (),
        raw_data_items=tuple(result.raw_data_items) if result is not None else (),
        metadata=metadata,
    )


def _cancelled_result(
    *,
    stage: str,
    engine: str,
    population_row: tuple[Any, ...],
    index: int,
    jobs_dir: Path,
    job: JobSpec | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
) -> JobResult:
    now = _now_text()
    job_name = _cancelled_job_name(index, now) if job is None else job.name
    job_dir = jobs_dir / job_name if job is None else job.directory
    metadata: dict[str, Any] = {
        "job_name": job_name,
        "status": "cancelled",
        "engine": engine,
        "failure_stage": stage,
        "error_type": "EvaluationCancelled",
        "error_message": "evaluation cancellation was requested",
        "cancelled_at": now,
        "population_index": index,
        "population_row": _metadata_row(population_row),
    }
    if run_id is not None:
        metadata["run_id"] = str(run_id)
    if optimization_index is not None:
        metadata["optimization_index"] = int(optimization_index)
    if generation_index is not None:
        metadata["generation_index"] = int(generation_index)
    return JobResult(
        job_name=job_name,
        job_dir=job_dir,
        status="cancelled",
        unnormalized_variables=(
            ()
            if job is None
            else tuple(float(value) for value in job.unnormalized_variables)
        ),
        normalized_variables=(
            _float_population_row(population_row)
            if job is None
            else tuple(float(value) for value in job.normalized_variables)
        ),
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


def _float_population_row(values: Iterable[Any]) -> tuple[float, ...]:
    try:
        return tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return ()


def _failure_job_name(index: int, timestamp: str) -> str:
    safe_stamp = timestamp.replace(":", "").replace(".", "").replace("+", "_")
    return f"failed_individual_{index}_{safe_stamp}"


def _cancelled_job_name(index: int, timestamp: str) -> str:
    safe_stamp = timestamp.replace(":", "").replace(".", "").replace("+", "_")
    return f"cancelled_individual_{index}_{safe_stamp}"


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _progress(message: str) -> None:
    if _progress_enabled():
        print(f"[yadof] {message}", flush=True)


class _PopulationProgress:
    """Render terminal outcomes for one generation or smoke population."""

    width = 28

    def __init__(
        self,
        *,
        total: int,
        mode: str,
        generation_index: int | None = None,
        phase: str | None = None,
    ) -> None:
        self.total = max(0, int(total))
        self.mode = str(mode)
        self.phase = (
            str(phase)
            if phase is not None
            else (
                f"generation {int(generation_index)}"
                if generation_index is not None
                else "population"
            )
        )
        self._enabled = _progress_enabled()
        self._outcomes: dict[int, bool] = {}
        self._last_state: tuple[int, int] | None = None
        self._line_open = False

    def start(self) -> None:
        self._render()

    def complete(self, index: int, *, successful: bool) -> None:
        if not self._enabled:
            return
        index = int(index)
        if not 0 <= index < self.total:
            return
        value = bool(successful)
        if self._outcomes.get(index) is value:
            return
        self._outcomes[index] = value
        self._render()

    def close(self) -> None:
        if self._line_open:
            print(file=sys.stderr)
            self._line_open = False

    def _render(self) -> None:
        if not self._enabled:
            return
        finished = len(self._outcomes)
        successful = sum(self._outcomes.values())
        state = (finished, successful)
        if state == self._last_state:
            return
        self._last_state = state
        errors = finished - successful
        remaining = max(0, self.total - finished)
        filled = (
            self.width
            if self.total == 0
            else int(self.width * finished / self.total)
        )
        bar = "#" * filled + "." * (self.width - filled)
        text = (
            f"[yadof] {self.phase} ({self.mode}) [{bar}] "
            f"{finished}/{self.total} successful={successful} "
            f"errors={errors} remaining={remaining}"
        )
        if sys.stderr.isatty():
            print(f"\r{text}", end="", file=sys.stderr, flush=True)
            self._line_open = True
            if remaining == 0:
                print(file=sys.stderr)
                self._line_open = False
            return
        print(text, file=sys.stderr, flush=True)


def _progress_enabled() -> bool:
    return str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


__all__ = [
    "evaluate",
    "evaluate_generation",
    "evaluate_population",
    "run_smoke_test",
]
