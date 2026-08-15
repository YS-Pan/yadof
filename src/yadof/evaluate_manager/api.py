"""Workspace-explicit fast, local, and distributed evaluation API."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..config import LoadedConfig, load_config
from ..job_template import get_objective_count, get_variable_count, validate_fast_task
from ..workspace import WorkspaceContext
from ..recorded_data.session import CampaignSession
from ..task_snapshot import GenerationTaskSnapshot
from .finalizer import finalize_result
from .job_files import prepare_job, validate_task_payload
from .job_result import write_metadata
from .local_runner import run_local_job
from .local_resources import plan_local_workers
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
    fast_max_workers: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
    _campaign_session: CampaignSession | None = None,
    _task_snapshot: GenerationTaskSnapshot | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Evaluate a population and return dynamic cost tuples in input order."""

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
    owns_session = _campaign_session is None
    if _campaign_session is None:
        live_config = load_config(workspace, overrides=overrides)
        session = CampaignSession(live_config)
        try:
            snapshot = session.begin_generation(live_config)
        except Exception:
            session.close()
            raise
        config = snapshot.config
    else:
        if _task_snapshot is None:
            raise ValueError("_task_snapshot is required with _campaign_session")
        session = _campaign_session
        snapshot = _task_snapshot
        config = snapshot.config
    selected_mode = str(config.EVALUATION_MODE).strip().lower()
    progress = _PopulationProgress(
        total=len(rows),
        mode=selected_mode,
        generation_index=generation_index,
    )
    progress.start()
    try:
        if selected_mode == "fast":
            if Path(python_executable).resolve() != Path(sys.executable).resolve():
                raise ValueError(
                    "fast evaluation workers use the current Python executable; "
                    "python_executable cannot select another runtime"
                )
            return _dispatch_fast(
                config,
                rows,
                timeout_sec=float(config.EVALUATION_TIMEOUT_SEC),
                env=env,
                fast_max_workers=int(config.FAST_EVALUATION_MAX_WORKERS),
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
                progress=progress,
                session=session,
                snapshot=snapshot,
            )
        if selected_mode == "distributed":
            return _dispatch_distributed(
                config,
                rows,
                timeout_sec=float(config.EVALUATION_TIMEOUT_SEC),
                env=env,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=generation_index,
                after_jobs_submitted=after_jobs_submitted,
                progress=progress,
                session=session,
                snapshot=snapshot,
            )
        if selected_mode != "local":
            raise ValueError(f"unsupported evaluation mode: {selected_mode!r}")
        return _dispatch_local(
            config,
            rows,
            timeout_sec=float(config.EVALUATION_TIMEOUT_SEC),
            python_executable=python_executable,
            env=env,
            local_max_workers=int(config.LOCAL_EVALUATION_MAX_WORKERS),
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            after_jobs_submitted=after_jobs_submitted,
            progress=progress,
            session=session,
            snapshot=snapshot,
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
    """Run exactly one deterministic representative individual with no timeout."""

    live_config = load_config(
        workspace,
        overrides={"EVALUATION_MODE": str(mode).strip().lower()},
    )
    session = CampaignSession(live_config)
    try:
        snapshot = session.begin_generation(live_config)
    except Exception:
        session.close()
        raise
    config = snapshot.config
    selected_mode = str(config.EVALUATION_MODE).strip().lower()
    if normalized_variables is None:
        normalized_variables = (0.5,) * get_variable_count(config.workspace)
    row = tuple(float(value) for value in normalized_variables)
    progress = _PopulationProgress(total=1, mode=selected_mode, phase="smoke")
    progress.start()
    try:
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
                progress=progress,
                session=session,
                snapshot=snapshot,
            )
        if selected_mode == "fast":
            return _dispatch_fast(
                config,
                (row,),
                timeout_sec=None,
                env=env,
                fast_max_workers=1,
                run_id=run_id,
                optimization_index=optimization_index,
                generation_index=None,
                progress=progress,
                session=session,
                snapshot=snapshot,
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
            progress=progress,
            session=session,
            snapshot=snapshot,
        )
    finally:
        progress.close()
        session.close()


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
) -> tuple[tuple[float, ...], ...]:
    from .fast_runner import run_fast_population

    validate_fast_task(config.workspace)
    rows = tuple(population)
    objective_width = get_objective_count(config.workspace)
    costs: list[tuple[float, ...] | None] = [None] * len(rows)

    def consume(index: int, result: JobResult) -> None:
        try:
            finalized = finalize_result(session, snapshot, result)
            if finalized.costs is not None:
                costs[index] = tuple(finalized.costs)
        finally:
            progress.complete(index, successful=costs[index] is not None)

    run_fast_population(
        config,
        rows,
        timeout_sec=timeout_sec,
        env=env,
        max_workers=fast_max_workers,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        on_result=consume,
    )
    session.flush_boundary()
    return tuple(
        row if row is not None else _inf_costs(objective_width) for row in costs
    )


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
) -> tuple[tuple[float, ...], ...]:
    validate_task_payload(config)
    population_rows = tuple(population)
    objective_width = get_objective_count(config.workspace)
    costs_by_individual: list[tuple[float, ...] | None] = [None] * len(population_rows)
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
        )

    worker_count = worker_plan.worker_count
    if worker_count <= 1 or len(population_rows) <= 1:
        for index, row in enumerate(population_rows):
            outcome = evaluate_one(index, row)
            finalized = finalize_result(session, snapshot, outcome[1])
            if finalized.costs is not None:
                costs_by_individual[index] = tuple(finalized.costs)
            progress.complete(index, successful=finalized.costs is not None)
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
                finalized = finalize_result(session, snapshot, outcome[1])
                if finalized.costs is not None:
                    costs_by_individual[index] = tuple(finalized.costs)
                progress.complete(index, successful=finalized.costs is not None)

    session.flush_boundary()
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
    worker_plan_metadata: Mapping[str, object],
) -> tuple[int, JobResult]:
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
        return index, failure

    try:
        result = run_local_job(
            job,
            timeout_sec=timeout_sec,
            python_executable=python_executable,
            env=env,
            plan_metadata=worker_plan_metadata,
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
) -> tuple[tuple[float, ...], ...]:
    from .condor_runner import run_condor_jobs

    validate_task_payload(config)
    rows = tuple(population)
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
            finalized = finalize_result(session, snapshot, failure)
            progress.complete(index, successful=finalized.costs is not None)
            continue
        jobs.append(job)
        positions.append(index)

    positions_by_job = {
        job.name: position for position, job in zip(positions, jobs)
    }

    finalized_by_job: dict[str, JobResult] = {}

    def consume_result(result: JobResult) -> None:
        finalized = finalize_result(session, snapshot, result)
        finalized_by_job[result.job_name] = finalized
        position = positions_by_job.get(result.job_name)
        if position is not None:
            if finalized.costs is not None:
                costs[position] = tuple(finalized.costs)
            progress.complete(position, successful=finalized.costs is not None)

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
        finalized = finalized_by_job.get(result.job_name)
        if finalized is None:
            finalized = finalize_result(session, snapshot, result)
            finalized_by_job[result.job_name] = finalized
        if finalized.costs is not None:
            costs[position] = tuple(finalized.costs)
        progress.complete(position, successful=finalized.costs is not None)
    for position in range(len(rows)):
        progress.complete(position, successful=costs[position] is not None)

    session.flush_boundary()
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
