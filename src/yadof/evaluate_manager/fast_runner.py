"""Reusable crash-isolated workers for memory-backed fast evaluation."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from io import StringIO
import json
import multiprocessing
from multiprocessing.connection import wait
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time
import traceback
from types import MappingProxyType
from typing import Any, Iterator
import uuid

from ..config import LoadedConfig
from ..job_template import (
    NamedRawDataItem,
    assign_parameters,
    get_parameter_definition_signature,
    validate_named_rawdata_items,
)
from ..task_loader import task_module
from ..workspace import WorkspaceContext
from .fast_resources import plan_fast_workers, validate_fast_configuration
from .job_result import tail
from .process_control import (
    process_tree_pids,
    terminate_descendants,
    terminate_process_tree,
)
from .types import JobResult


ResultConsumer = Callable[[int, JobResult], object]


@dataclass(frozen=True)
class _FastTask:
    index: int
    name: str
    normalized_variables: tuple[float, ...]
    unnormalized_variables: tuple[float, ...]
    parameter_values: tuple[tuple[str, float], ...]


@dataclass
class _ActiveTask:
    task: _FastTask
    scratch_dir: Path
    started_monotonic: float | None
    started_at: str
    observed_pids: set[int] = field(default_factory=set)
    peak_process_count: int = 1


@dataclass
class _WorkerSlot:
    index: int
    process: multiprocessing.Process
    connection: Any
    active: _ActiveTask | None = None


def run_fast_population(
    config: LoadedConfig,
    population: Sequence[tuple[float, ...]],
    *,
    timeout_sec: float | None,
    env: Mapping[str, str] | None,
    max_workers: int,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    on_result: ResultConsumer,
) -> None:
    """Execute and stream results to the submit-side recording boundary."""

    scratch_root = validate_fast_configuration(config)
    task_signature = _fast_task_signature(config)
    pending: deque[_FastTask] = deque()
    for index, row in enumerate(population):
        name = _logical_evaluation_name(index)
        try:
            assigned = assign_parameters(config.workspace, row)
        except Exception as exc:  # noqa: BLE001 - isolate assignment per candidate.
            on_result(
                index,
                _parent_failure_result(
                    index=index,
                    name=name,
                    normalized_variables=row,
                    unnormalized_variables=(),
                    status="error",
                    failure_stage="parameter_assignment",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    run_id=run_id,
                    optimization_index=optimization_index,
                    generation_index=generation_index,
                    task_signature=task_signature,
                ),
            )
            continue
        pending.append(
            _FastTask(
                index=index,
                name=name,
                normalized_variables=tuple(float(value) for value in row),
                unnormalized_variables=tuple(
                    float(parameter.value) for parameter in assigned
                ),
                parameter_values=tuple(
                    (str(parameter.name), float(parameter.value))
                    for parameter in assigned
                ),
            )
        )
    if not pending:
        return

    plan = plan_fast_workers(
        config,
        population_size=len(pending),
        configured_max=max_workers,
    )
    plan_metadata = plan.metadata()
    scratch_existed = scratch_root.exists()
    scratch_root.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    slots = [
        _spawn_worker(context, slot_index, config.workspace)
        for slot_index in range(plan.worker_count)
    ]
    try:
        while pending or any(slot.active is not None for slot in slots):
            for slot in slots:
                if slot.active is None and pending:
                    _assign_task(
                        slot,
                        pending.popleft(),
                        scratch_root=scratch_root,
                        timeout_sec=timeout_sec,
                        env=env,
                        run_id=run_id,
                        optimization_index=optimization_index,
                        generation_index=generation_index,
                        task_signature=task_signature,
                    )

            busy = [slot for slot in slots if slot.active is not None]
            if not busy:
                continue
            for slot in busy:
                _observe_worker_tree(slot)
            ready_connections = set(
                wait([slot.connection for slot in busy], timeout=0.05)
            )
            for slot_index, slot in enumerate(tuple(slots)):
                active = slot.active
                if active is None:
                    continue
                if slot.connection in ready_connections:
                    try:
                        response = slot.connection.recv()
                    except (EOFError, OSError):
                        response = None
                    if (
                        response is not None
                        and response.get("message_type") == "started"
                    ):
                        active.started_monotonic = time.monotonic()
                        active.started_at = str(
                            response.get("worker_started_at") or active.started_at
                        )
                        _observe_worker_tree(slot)
                        continue
                    if response is not None:
                        _observe_worker_tree(slot)
                        terminate_descendants(
                            slot.process.pid,
                            known_descendant_pids=active.observed_pids,
                        )
                        result = _result_from_worker_response(
                            slot,
                            response,
                            run_id=run_id,
                            optimization_index=optimization_index,
                            generation_index=generation_index,
                            task_signature=task_signature,
                            plan_metadata=plan_metadata,
                        )
                        cleanup_error = _cleanup_scratch(active.scratch_dir)
                        result = _with_cleanup_diagnostic(result, cleanup_error)
                        on_result(active.task.index, result)
                        slot.active = None
                        if result.status != "done":
                            slots[slot_index] = _replace_worker(
                                context, slot, config.workspace
                            )
                        continue

                elapsed = _active_elapsed(active)
                if (
                    active.started_monotonic is not None
                    and timeout_sec is not None
                    and elapsed >= float(timeout_sec)
                ):
                    terminate_process_tree(
                        slot.process.pid,
                        known_descendant_pids=active.observed_pids,
                    )
                    slot.process.join(timeout=2.0)
                    cleanup_error = _cleanup_scratch(active.scratch_dir)
                    result = _parent_failure_result(
                        index=active.task.index,
                        name=active.task.name,
                        normalized_variables=active.task.normalized_variables,
                        unnormalized_variables=active.task.unnormalized_variables,
                        status="timeout",
                        failure_stage="timeout",
                        error_type="FastEvaluationTimeout",
                        error_message=(
                            "fast task exceeded timeout_sec="
                            f"{float(timeout_sec):.3f}"
                        ),
                        run_id=run_id,
                        optimization_index=optimization_index,
                        generation_index=generation_index,
                        task_signature=task_signature,
                        worker_pid=slot.process.pid,
                        started_at=active.started_at,
                        elapsed_sec=elapsed,
                        observed_pids=active.observed_pids,
                        peak_process_count=active.peak_process_count,
                        plan_metadata=plan_metadata,
                        cleanup_error=cleanup_error,
                    )
                    on_result(active.task.index, result)
                    slot.active = None
                    slots[slot_index] = _replace_worker(
                        context, slot, config.workspace
                    )
                    continue

                if not slot.process.is_alive():
                    terminate_process_tree(
                        slot.process.pid,
                        known_descendant_pids=active.observed_pids,
                    )
                    cleanup_error = _cleanup_scratch(active.scratch_dir)
                    result = _parent_failure_result(
                        index=active.task.index,
                        name=active.task.name,
                        normalized_variables=active.task.normalized_variables,
                        unnormalized_variables=active.task.unnormalized_variables,
                        status="error",
                        failure_stage="worker_exit",
                        error_type="FastWorkerExit",
                        error_message=(
                            "fast worker exited without a result; "
                            f"exitcode={slot.process.exitcode!r}"
                        ),
                        run_id=run_id,
                        optimization_index=optimization_index,
                        generation_index=generation_index,
                        task_signature=task_signature,
                        worker_pid=slot.process.pid,
                        worker_exitcode=slot.process.exitcode,
                        started_at=active.started_at,
                        elapsed_sec=elapsed,
                        observed_pids=active.observed_pids,
                        peak_process_count=active.peak_process_count,
                        plan_metadata=plan_metadata,
                        cleanup_error=cleanup_error,
                    )
                    on_result(active.task.index, result)
                    slot.active = None
                    slots[slot_index] = _replace_worker(
                        context, slot, config.workspace
                    )
    finally:
        for slot in slots:
            _stop_worker(slot)
        if not scratch_existed:
            try:
                scratch_root.rmdir()
            except OSError:
                pass


def _spawn_worker(
    context: multiprocessing.context.BaseContext,
    slot_index: int,
    workspace: WorkspaceContext,
) -> _WorkerSlot:
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_fast_worker_main,
        args=(child_connection, workspace),
        name=f"yadof-fast-worker-{slot_index}",
        daemon=False,
    )
    process.start()
    child_connection.close()
    return _WorkerSlot(slot_index, process, parent_connection)


def _replace_worker(
    context: multiprocessing.context.BaseContext,
    slot: _WorkerSlot,
    workspace: WorkspaceContext,
) -> _WorkerSlot:
    _stop_worker(slot)
    return _spawn_worker(context, slot.index, workspace)


def _stop_worker(slot: _WorkerSlot) -> None:
    if slot.process.is_alive() and slot.active is None:
        try:
            slot.connection.send(None)
        except (BrokenPipeError, EOFError, OSError):
            pass
        slot.process.join(timeout=2.0)
    if slot.process.is_alive():
        known = slot.active.observed_pids if slot.active is not None else ()
        terminate_process_tree(
            slot.process.pid,
            known_descendant_pids=known,
        )
        slot.process.join(timeout=2.0)
    try:
        slot.connection.close()
    except OSError:
        pass


def _assign_task(
    slot: _WorkerSlot,
    task: _FastTask,
    *,
    scratch_root: Path,
    timeout_sec: float | None,
    env: Mapping[str, str] | None,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    task_signature: str,
) -> None:
    scratch_dir = Path(
        tempfile.mkdtemp(
            prefix=f"candidate_{task.index}_",
            dir=str(scratch_root),
        )
    )
    started_at = _now_text()
    request = {
        "name": task.name,
        "parameter_values": task.parameter_values,
        "normalized_variables": task.normalized_variables,
        "scratch_dir": str(scratch_dir),
        "timeout_sec": timeout_sec,
        "environment": dict(env or {}),
        "run_id": run_id,
        "optimization_index": optimization_index,
        "generation_index": generation_index,
        "population_index": task.index,
        "task_static_signature": task_signature,
    }
    try:
        slot.connection.send(request)
    except Exception:
        _cleanup_scratch(scratch_dir)
        raise
    slot.active = _ActiveTask(
        task=task,
        scratch_dir=scratch_dir,
        started_monotonic=None,
        started_at=started_at,
        observed_pids={slot.process.pid},
    )


def _observe_worker_tree(slot: _WorkerSlot) -> None:
    if slot.active is None:
        return
    pids = process_tree_pids(slot.process.pid)
    slot.active.observed_pids.update(pids)
    slot.active.peak_process_count = max(
        slot.active.peak_process_count,
        len(pids),
    )


def _fast_worker_main(connection: Any, workspace: WorkspaceContext) -> None:
    try:
        while True:
            request = connection.recv()
            if request is None:
                return
            connection.send(
                {
                    "message_type": "started",
                    "worker_started_at": _now_text(),
                }
            )
            response = _execute_worker_request(workspace, request)
            connection.send(response)
            if str(response.get("status")) != "done":
                return
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        try:
            connection.close()
        except OSError:
            pass


def _execute_worker_request(
    workspace: WorkspaceContext,
    request: Mapping[str, object],
) -> dict[str, object]:
    started_monotonic = time.monotonic()
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    environment = {
        str(key): str(value)
        for key, value in dict(request.get("environment") or {}).items()
    }
    context_values = {
        "evaluation_name": str(request["name"]),
        "scratch_dir": Path(str(request["scratch_dir"])),
        "timeout_sec": request.get("timeout_sec"),
        "environment": MappingProxyType(environment),
        "run_id": request.get("run_id"),
        "optimization_index": request.get("optimization_index"),
        "generation_index": request.get("generation_index"),
        "population_index": request.get("population_index"),
        "task_static_signature": request.get("task_static_signature"),
    }
    parameters = MappingProxyType(
        {
            str(name): float(value)
            for name, value in request.get("parameter_values", ())
        }
    )
    try:
        with (
            _temporary_environment(environment),
            redirect_stdout(stdout_buffer),
            redirect_stderr(stderr_buffer),
            task_module(workspace, "evaluation") as module,
        ):
            evaluate_rawdata = getattr(module, "evaluate_rawdata")
            output = evaluate_rawdata(
                parameters,
                MappingProxyType(context_values),
            )
        rawdata_output, diagnostics = _split_task_output(output)
        raw_data_items = validate_named_rawdata_items(rawdata_output)
        task_diagnostics = _json_diagnostics(diagnostics)
        return {
            "status": "done",
            "raw_data_items": raw_data_items,
            "task_diagnostics": task_diagnostics,
            "worker_pid": os.getpid(),
            "execute_machine": socket.gethostname(),
            "worker_finished_at": _now_text(),
            "worker_elapsed_sec": time.monotonic() - started_monotonic,
            "worker_stdout_tail": tail(stdout_buffer.getvalue()),
            "worker_stderr_tail": tail(stderr_buffer.getvalue()),
        }
    except BaseException as exc:  # noqa: BLE001 - worker failure is data.
        return {
            "status": "error",
            "failure_stage": "task_kernel",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback_tail": tail(traceback.format_exc(), limit=8000),
            "worker_pid": os.getpid(),
            "execute_machine": socket.gethostname(),
            "worker_finished_at": _now_text(),
            "worker_elapsed_sec": time.monotonic() - started_monotonic,
            "worker_stdout_tail": tail(stdout_buffer.getvalue()),
            "worker_stderr_tail": tail(stderr_buffer.getvalue()),
        }


def _split_task_output(
    output: object,
) -> tuple[Mapping[str, Mapping[str, object]], Mapping[str, object]]:
    diagnostics: Mapping[str, object] = {}
    rawdata_output = output
    if isinstance(output, tuple):
        if len(output) != 2:
            raise TypeError(
                "evaluate_rawdata() tuple result must be (rawdata_items, diagnostics)"
            )
        rawdata_output, diagnostics = output
    if not isinstance(rawdata_output, Mapping):
        raise TypeError(
            "evaluate_rawdata() must return a rawData mapping or "
            "(rawData mapping, diagnostics mapping)"
        )
    if not isinstance(diagnostics, Mapping):
        raise TypeError("fast task diagnostics must be a mapping")
    return rawdata_output, diagnostics


def _json_diagnostics(value: Mapping[str, object]) -> dict[str, object]:
    try:
        return json.loads(json.dumps(dict(value), ensure_ascii=True))
    except (TypeError, ValueError) as exc:
        raise TypeError("fast task diagnostics must be JSON-serializable") from exc


@contextmanager
def _temporary_environment(values: Mapping[str, str]) -> Iterator[None]:
    previous = {name: os.environ.get(name) for name in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for name, old_value in previous.items():
            if old_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old_value


def _result_from_worker_response(
    slot: _WorkerSlot,
    response: Mapping[str, object],
    *,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    task_signature: str,
    plan_metadata: Mapping[str, object],
) -> JobResult:
    active = slot.active
    if active is None:  # pragma: no cover - internal scheduler invariant.
        raise RuntimeError("fast worker response has no active task")
    finished_at = _now_text()
    status = str(response.get("status", "error"))
    response_metadata = dict(response)
    raw_data_items = tuple(response_metadata.pop("raw_data_items", ()))
    metadata: dict[str, object] = {
        "job_name": active.task.name,
        "status": status,
        "engine": "fast",
        "started_at": active.started_at,
        "ended_at": finished_at,
        "elapsed_time": _active_elapsed(active),
        "population_index": active.task.index,
        "population_row": list(active.task.normalized_variables),
        "task_static_signature": task_signature,
        "fast_worker_pid": slot.process.pid,
        "fast_peak_process_count": active.peak_process_count,
        "fast_observed_process_pids": sorted(active.observed_pids),
        **dict(plan_metadata),
        **response_metadata,
    }
    _add_evaluation_identity(
        metadata,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
    )
    return JobResult(
        job_name=active.task.name,
        job_dir=None,
        status=status,
        unnormalized_variables=active.task.unnormalized_variables,
        normalized_variables=active.task.normalized_variables,
        raw_data_items=tuple(
            item for item in raw_data_items if isinstance(item, NamedRawDataItem)
        ),
        metadata=metadata,
    )


def _parent_failure_result(
    *,
    index: int,
    name: str,
    normalized_variables: Sequence[float],
    unnormalized_variables: Sequence[float],
    status: str,
    failure_stage: str,
    error_type: str,
    error_message: str,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    task_signature: str,
    worker_pid: int | None = None,
    worker_exitcode: int | None = None,
    started_at: str | None = None,
    elapsed_sec: float | None = None,
    observed_pids: Sequence[int] | set[int] = (),
    peak_process_count: int | None = None,
    plan_metadata: Mapping[str, object] | None = None,
    cleanup_error: str | None = None,
) -> JobResult:
    now = _now_text()
    metadata: dict[str, object] = {
        "job_name": name,
        "status": status,
        "engine": "fast",
        "failure_stage": failure_stage,
        "error_type": error_type,
        "error_message": error_message,
        "started_at": started_at or now,
        "ended_at": now,
        "population_index": index,
        "population_row": [float(value) for value in normalized_variables],
        "task_static_signature": task_signature,
        **dict(plan_metadata or {}),
    }
    if elapsed_sec is not None:
        metadata["elapsed_time"] = max(0.0, float(elapsed_sec))
    if worker_pid is not None:
        metadata["fast_worker_pid"] = int(worker_pid)
    if worker_exitcode is not None:
        metadata["fast_worker_exitcode"] = int(worker_exitcode)
    if observed_pids:
        metadata["fast_observed_process_pids"] = sorted(
            int(pid) for pid in observed_pids
        )
    if peak_process_count is not None:
        metadata["fast_peak_process_count"] = int(peak_process_count)
    if cleanup_error is not None:
        metadata["scratch_cleanup_error"] = cleanup_error
    _add_evaluation_identity(
        metadata,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
    )
    return JobResult(
        job_name=name,
        job_dir=None,
        status=status,
        unnormalized_variables=tuple(float(value) for value in unnormalized_variables),
        normalized_variables=tuple(float(value) for value in normalized_variables),
        metadata=metadata,
    )


def _with_cleanup_diagnostic(
    result: JobResult, cleanup_error: str | None
) -> JobResult:
    if cleanup_error is None:
        return result
    metadata = dict(result.metadata)
    metadata["scratch_cleanup_error"] = cleanup_error
    return JobResult(
        job_name=result.job_name,
        job_dir=result.job_dir,
        status=result.status,
        unnormalized_variables=result.unnormalized_variables,
        normalized_variables=result.normalized_variables,
        raw_data_paths=result.raw_data_paths,
        raw_data_items=result.raw_data_items,
        metadata=metadata,
        costs=result.costs,
    )


def _cleanup_scratch(path: Path) -> str | None:
    if not path.exists():
        return None
    last_error: OSError | None = None
    for _attempt in range(4):
        try:
            shutil.rmtree(path)
            return None
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    return f"{type(last_error).__name__}: {last_error}"


def _active_elapsed(active: _ActiveTask) -> float:
    if active.started_monotonic is None:
        return 0.0
    return max(0.0, time.monotonic() - active.started_monotonic)


def _fast_task_signature(config: LoadedConfig) -> str:
    digest = hashlib.sha256()
    definition = get_parameter_definition_signature(config.workspace)
    digest.update(
        json.dumps(
            definition,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    root = config.workspace.job_template_dir
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {"__pycache__", ".pytest_cache", "rawData"} for part in relative.parts):
            continue
        if relative.as_posix() == "parameters_constraints.py":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _add_evaluation_identity(
    metadata: dict[str, object],
    *,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
) -> None:
    if run_id is not None:
        metadata["run_id"] = str(run_id)
    if optimization_index is not None:
        metadata["optimization_index"] = int(optimization_index)
    if generation_index is not None:
        metadata["generation_index"] = int(generation_index)


def _logical_evaluation_name(index: int) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"fast_{stamp}_{int(index)}_{uuid.uuid4().hex[:8]}"


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


__all__ = ["run_fast_population"]
