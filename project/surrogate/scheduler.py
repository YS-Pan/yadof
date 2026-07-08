from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import threading

from project import config

from . import metadata as surrogate_metadata


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yadof-surrogate")
_LOCK = threading.RLock()
_PENDING: Future | None = None
_PENDING_GENERATION: int | None = None
_LAST_COMPLETED_GENERATION: int | None = None
_LAST_ERROR: str | None = None


@dataclass(frozen=True)
class TrainingScheduleStatus:
    action: str
    generation_index: int | None = None
    pending_generation_index: int | None = None
    latest_completed_generation_index: int | None = None
    error: str = ""


def has_trained_state() -> bool:
    from . import runtime

    return runtime.has_trained_state()


def latest_completed_generation_index() -> int | None:
    from . import runtime

    state_generation = runtime.latest_state_generation()
    with _LOCK:
        candidates = [
            value
            for value in (state_generation, _LAST_COMPLETED_GENERATION)
            if value is not None
        ]
    return max(candidates) if candidates else None


def wait_for_pending_training() -> TrainingScheduleStatus:
    future, pending_generation = _pending_snapshot()
    if future is None:
        return _status("idle")
    try:
        future.result()
    except Exception as exc:  # noqa: BLE001 - training failures should degrade to baseline optimization.
        return _status("failed", generation_index=pending_generation, error=f"{exc.__class__.__name__}: {exc}")
    return _status("completed", generation_index=pending_generation)


def start_training(generation_index: int, *, block: bool = False) -> TrainingScheduleStatus:
    global _PENDING, _PENDING_GENERATION

    if block:
        wait_for_pending_training()
        return _train_blocking(int(generation_index))

    with _LOCK:
        _refresh_finished_locked()
        if _PENDING is not None and not _PENDING.done():
            return _status_locked("already_running", generation_index=int(generation_index))
        future = _EXECUTOR.submit(_train_in_background, int(generation_index))
        _PENDING = future
        _PENDING_GENERATION = int(generation_index)
        future.add_done_callback(_training_done)
        return _status_locked("started", generation_index=int(generation_index))


def ensure_fresh_enough(generation_index: int) -> TrainingScheduleStatus:
    max_lag = max(0, int(getattr(config, "OPTIMIZE_SURROGATE_MAX_TRAINING_LAG", 2)))
    generation = int(generation_index)
    latest = latest_completed_generation_index()
    virtual_latest = -1 if latest is None else int(latest)
    if generation - virtual_latest <= max_lag:
        return _status("fresh", generation_index=generation)

    waited = wait_for_pending_training()
    latest = latest_completed_generation_index()
    virtual_latest = -1 if latest is None else int(latest)
    if generation - virtual_latest <= max_lag:
        return _status("waited", generation_index=generation, error=waited.error)

    return _train_blocking(generation)


def _train_blocking(generation_index: int) -> TrainingScheduleStatus:
    global _LAST_COMPLETED_GENERATION, _LAST_ERROR

    started_at = surrogate_metadata.now_text()
    try:
        from . import runtime

        state = runtime.train(generation_index=int(generation_index), started_at=started_at)
    except Exception as exc:  # noqa: BLE001 - optimizer can fall back after a failed required refresh.
        surrogate_metadata.record_training_failure(
            generation_index=int(generation_index),
            exc=exc,
            started_at=started_at,
        )
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            _LAST_ERROR = error
        return _status("failed", generation_index=int(generation_index), error=error)

    with _LOCK:
        _LAST_COMPLETED_GENERATION = int(state.generation_index)
        _LAST_ERROR = ""
    return _status("trained_blocking", generation_index=int(generation_index))


def _train_in_background(generation_index: int):
    started_at = surrogate_metadata.now_text()
    from . import runtime

    return runtime.train(generation_index=int(generation_index), started_at=started_at)


def _training_done(future: Future) -> None:
    global _LAST_COMPLETED_GENERATION, _LAST_ERROR, _PENDING, _PENDING_GENERATION

    with _LOCK:
        generation = _PENDING_GENERATION
    try:
        state = future.result()
    except Exception as exc:  # noqa: BLE001 - preserve failure metadata and allow optimizer fallback.
        surrogate_metadata.record_training_failure(
            generation_index=-1 if generation is None else int(generation),
            exc=exc,
        )
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            _LAST_ERROR = error
            if future is _PENDING:
                _PENDING = None
                _PENDING_GENERATION = None
        return

    with _LOCK:
        _LAST_COMPLETED_GENERATION = int(state.generation_index)
        _LAST_ERROR = ""
        if future is _PENDING:
            _PENDING = None
            _PENDING_GENERATION = None


def _pending_snapshot() -> tuple[Future | None, int | None]:
    with _LOCK:
        _refresh_finished_locked()
        return _PENDING, _PENDING_GENERATION


def _refresh_finished_locked() -> None:
    global _PENDING, _PENDING_GENERATION
    if _PENDING is not None and _PENDING.done():
        return
    if _PENDING is None:
        _PENDING_GENERATION = None


def _status(
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    with _LOCK:
        return _status_locked(action, generation_index=generation_index, error=error)


def _status_locked(
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    return TrainingScheduleStatus(
        action=str(action),
        generation_index=generation_index,
        pending_generation_index=_PENDING_GENERATION,
        latest_completed_generation_index=latest_completed_generation_index(),
        error=str(error or _LAST_ERROR or ""),
    )
