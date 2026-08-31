"""Backend-neutral ownership and state for one bounded evaluation batch."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import threading
import time
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping
import uuid

from ..config import LoadedConfig
from ..workspace import WorkspaceContext
from .types import EvaluationResult, JobResult

if TYPE_CHECKING:
    from ..recorded_data.session import CampaignSession
    from ..task_snapshot import GenerationTaskSnapshot


class EvaluationHandleState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class EvaluationBatch:
    """Materialized inputs and frozen configuration without runtime resources."""

    workspace: WorkspaceContext
    population: tuple[tuple[Any, ...], ...]
    config: LoadedConfig = field(repr=False, compare=False)
    mode: str
    timeout_sec: float | None
    python_executable: Path
    environment: tuple[tuple[str, str], ...]
    local_max_workers: int
    fast_max_workers: int
    objective_width: int
    run_id: str | None = None
    optimization_index: int | None = None
    generation_index: int | None = None
    batch_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    phase: str = "evaluation"
    _campaign_session: CampaignSession | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _task_snapshot: GenerationTaskSnapshot | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    def __post_init__(self) -> None:
        mode = str(self.mode).strip().lower()
        if mode not in {"fast", "local", "distributed"}:
            raise ValueError(f"unsupported evaluation mode: {mode!r}")
        if int(self.objective_width) <= 0:
            raise ValueError("objective_width must be positive")
        if int(self.local_max_workers) <= 0 or int(self.fast_max_workers) <= 0:
            raise ValueError("evaluation worker limits must be positive")
        if bool(self._campaign_session is None) != bool(self._task_snapshot is None):
            raise ValueError("campaign session and task snapshot must be supplied together")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "population", tuple(tuple(row) for row in self.population))
        object.__setattr__(self, "python_executable", Path(self.python_executable))
        object.__setattr__(
            self,
            "environment",
            tuple((str(key), str(value)) for key, value in self.environment),
        )
        object.__setattr__(self, "objective_width", int(self.objective_width))
        object.__setattr__(self, "local_max_workers", int(self.local_max_workers))
        object.__setattr__(self, "fast_max_workers", int(self.fast_max_workers))
        object.__setattr__(self, "batch_id", str(self.batch_id))

    @property
    def env(self) -> Mapping[str, str] | None:
        if not self.environment:
            return None
        return MappingProxyType(dict(self.environment))

    @property
    def uses_campaign_scope(self) -> bool:
        return self._campaign_session is not None


class EvaluationHandle:
    """Thread-safe owner of one evaluation batch and all terminal cleanup."""

    def __init__(self, batch: EvaluationBatch) -> None:
        if not isinstance(batch, EvaluationBatch):
            raise TypeError("batch must be an EvaluationBatch")
        self.batch = batch
        self._state = EvaluationHandleState.CREATED
        self._state_lock = threading.RLock()
        self._close_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._terminal_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._result: EvaluationResult | None = None
        self._failure: BaseException | None = None
        self._started_at_monotonic: float | None = None
        self._terminal_at_monotonic: float | None = None
        self._cancel_requested_at_monotonic: float | None = None
        self._closed_at_monotonic: float | None = None
        self._registered_session = batch._campaign_session
        if self._registered_session is not None:
            self._registered_session._register_generation_handle(  # noqa: SLF001
                batch._task_snapshot,
                self,
                boundary_policy="cancel",
            )

    @property
    def state(self) -> EvaluationHandleState:
        with self._state_lock:
            return self._state

    @property
    def diagnostics(self) -> Mapping[str, object]:
        with self._state_lock:
            values: dict[str, object] = {
                "batch_id": self.batch.batch_id,
                "mode": self.batch.mode,
                "candidate_count": len(self.batch.population),
                "state": self._state.value,
                "cancel_requested": self._cancel_event.is_set(),
                "worker_alive": bool(self._thread and self._thread.is_alive()),
            }
            if self._started_at_monotonic is not None:
                values["started_at_monotonic"] = self._started_at_monotonic
            if self._cancel_requested_at_monotonic is not None:
                values["cancel_requested_at_monotonic"] = (
                    self._cancel_requested_at_monotonic
                )
            if self._terminal_at_monotonic is not None:
                values["terminal_at_monotonic"] = self._terminal_at_monotonic
            if self._closed_at_monotonic is not None:
                values["closed_at_monotonic"] = self._closed_at_monotonic
            return MappingProxyType(values)

    def start(self) -> EvaluationHandle:
        """Start exactly once; repeated calls after start return this handle."""

        with self._state_lock:
            if self._state == EvaluationHandleState.CLOSED:
                raise RuntimeError("cannot start a closed evaluation handle")
            if self._state == EvaluationHandleState.COMPLETED and self._thread is None:
                raise RuntimeError("cannot start an evaluation cancelled before start")
            if self._state != EvaluationHandleState.CREATED:
                return self
            self._state = EvaluationHandleState.RUNNING
            self._started_at_monotonic = time.monotonic()
            thread = threading.Thread(
                target=self._run,
                name=f"yadof-evaluation-{self.batch.batch_id[:12]}",
                daemon=False,
            )
            self._thread = thread
        try:
            thread.start()
        except BaseException as exc:
            with self._state_lock:
                self._failure = exc
                self._state = EvaluationHandleState.FAILED
                self._terminal_at_monotonic = time.monotonic()
                self._terminal_event.set()
            raise
        return self

    def wait(self, timeout: float | None = None) -> EvaluationResult:
        """Wait for the durable terminal result without changing lifecycle state."""

        with self._state_lock:
            if self._state == EvaluationHandleState.CREATED:
                raise RuntimeError("evaluation handle has not been started")
        if not self._terminal_event.wait(timeout):
            raise TimeoutError(f"evaluation batch {self.batch.batch_id} is still running")
        with self._state_lock:
            failure = self._failure
            result = self._result
        if failure is not None:
            raise failure
        if result is None:
            raise RuntimeError("evaluation handle reached terminal state without a result")
        return result

    def cancel(self) -> bool:
        """Request best-effort cancellation; return true only for the first request."""

        with self._state_lock:
            if self._state in {
                EvaluationHandleState.COMPLETED,
                EvaluationHandleState.FAILED,
                EvaluationHandleState.CLOSED,
            }:
                return False
            if self._cancel_event.is_set():
                return False
            self._cancel_event.set()
            self._cancel_requested_at_monotonic = time.monotonic()
            if self._state == EvaluationHandleState.CREATED:
                self._result = _cancelled_before_start(self.batch)
                self._state = EvaluationHandleState.COMPLETED
                self._terminal_at_monotonic = time.monotonic()
                self._terminal_event.set()
                return True
            self._state = EvaluationHandleState.CANCELLING
            return True

    def close(self) -> None:
        """Cancel active work, wait for cleanup, and release the generation lease."""

        with self._close_lock:
            with self._state_lock:
                already_closed = self._state == EvaluationHandleState.CLOSED
                failure = self._failure
            if already_closed:
                if failure is not None:
                    raise failure
                return
            self.cancel()
            terminal_failure: BaseException | None = None
            try:
                self.wait()
            except BaseException as exc:  # Preserve close after framework failure.
                terminal_failure = exc
            finally:
                with self._state_lock:
                    self._state = EvaluationHandleState.CLOSED
                    self._closed_at_monotonic = time.monotonic()
                self._unregister()
            if terminal_failure is not None:
                raise terminal_failure

    def _run(self) -> None:
        try:
            from .api import _execute_evaluation_batch

            result = _execute_evaluation_batch(self.batch, self._cancel_event)
        except BaseException as exc:  # The owner thread must wake every waiter.
            with self._state_lock:
                self._failure = exc
                self._state = EvaluationHandleState.FAILED
                self._terminal_at_monotonic = time.monotonic()
                self._terminal_event.set()
            return
        with self._state_lock:
            self._result = result
            self._state = EvaluationHandleState.COMPLETED
            self._terminal_at_monotonic = time.monotonic()
            self._terminal_event.set()

    def _unregister(self) -> None:
        session = self._registered_session
        if session is None:
            return
        self._registered_session = None
        session._unregister_generation_handle(self)  # noqa: SLF001

    def __enter__(self) -> EvaluationHandle:
        if self.state == EvaluationHandleState.CREATED:
            self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            self.close()
        except BaseException as close_error:
            if exc is None:
                raise
            add_note = getattr(exc, "add_note", None)
            if callable(add_note):
                add_note(
                    "evaluation cleanup also failed: "
                    f"{type(close_error).__name__}: {close_error}"
                )
        return False


def _cancelled_before_start(batch: EvaluationBatch) -> EvaluationResult:
    rows = tuple(
        JobResult(
            job_name=f"cancelled_{batch.batch_id[:12]}_{index:06d}",
            job_dir=None,
            status="cancelled",
            unnormalized_variables=(),
            normalized_variables=_float_row(row),
            metadata={
                "status": "cancelled",
                "failure_stage": "before_start",
                "error_type": "EvaluationCancelled",
                "error_message": "evaluation was cancelled before start",
                "cancelled_at": _now_text(),
                "evaluation_batch_id": batch.batch_id,
                "population_index": index,
                "population_row": [_metadata_value(value) for value in row],
                "evidence_state": "not_started",
                "interpretation_state": "not_applicable",
            },
        )
        for index, row in enumerate(batch.population)
    )
    return EvaluationResult(
        batch_id=batch.batch_id,
        mode=batch.mode,
        rows=rows,
        objective_width=batch.objective_width,
        cancel_requested=True,
        diagnostics={
            "candidate_count": len(rows),
            "status_counts": {"cancelled": len(rows)},
            "terminal_reason": "cancelled_before_start",
        },
    )


def _float_row(row: tuple[Any, ...]) -> tuple[float, ...]:
    try:
        return tuple(float(value) for value in row)
    except (TypeError, ValueError):
        return ()


def _metadata_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)[:512]


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


__all__ = ["EvaluationBatch", "EvaluationHandle", "EvaluationHandleState"]
