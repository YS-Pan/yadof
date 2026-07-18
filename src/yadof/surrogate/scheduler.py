from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import threading

from ..config import LoadedConfig, load_config
from ..workspace import WorkspaceContext
from . import metadata as surrogate_metadata
from . import runtime


WorkspaceLike = WorkspaceContext | str | Path


@dataclass
class _WorkspaceSchedule:
    pending: Future | None = None
    pending_generation: int | None = None
    last_completed_generation: int | None = None
    last_error: str = ""


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yadof-surrogate")
_LOCK = threading.RLock()
_SCHEDULES: dict[runtime.StateKey, _WorkspaceSchedule] = {}


@dataclass(frozen=True)
class TrainingScheduleStatus:
    action: str
    generation_index: int | None = None
    pending_generation_index: int | None = None
    latest_completed_generation_index: int | None = None
    error: str = ""


def has_trained_state(workspace: WorkspaceLike) -> bool:
    return runtime.has_trained_state(workspace)


def latest_completed_generation_index(workspace: WorkspaceLike) -> int | None:
    config = load_config(workspace)
    key = runtime.workspace_state_key(config)
    state_generation = runtime.latest_state_generation(config.workspace)
    with _LOCK:
        schedule = _SCHEDULES.get(key)
        candidates = [
            value
            for value in (
                state_generation,
                None if schedule is None else schedule.last_completed_generation,
            )
            if value is not None
        ]
    return max(candidates) if candidates else None


def wait_for_pending_training(workspace: WorkspaceLike) -> TrainingScheduleStatus:
    config = load_config(workspace)
    key = runtime.workspace_state_key(config)
    with _LOCK:
        schedule = _schedule_locked(key)
        future = schedule.pending
        pending_generation = schedule.pending_generation
    if future is None:
        return _status(config, key, "idle")
    try:
        state = future.result()
    except Exception as exc:  # noqa: BLE001 - optimizer falls back to real evaluation.
        return _status(
            config,
            key,
            "failed",
            generation_index=pending_generation,
            error=f"{exc.__class__.__name__}: {exc}",
        )
    with _LOCK:
        schedule = _schedule_locked(key)
        schedule.last_completed_generation = int(state.generation_index)
        schedule.last_error = ""
        if future is schedule.pending:
            schedule.pending = None
            schedule.pending_generation = None
    return _status(
        config, key, "completed", generation_index=pending_generation
    )


def start_training(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    block: bool = False,
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    key = runtime.workspace_state_key(config)
    generation = int(generation_index)

    if block:
        wait_for_pending_training(config.workspace)
        return _train_blocking(config, key, generation)

    with _LOCK:
        schedule = _schedule_locked(key)
        _refresh_finished_locked(schedule)
        if schedule.pending is not None and not schedule.pending.done():
            return _status_locked(
                config, key, "already_running", generation_index=generation
            )
        future = _EXECUTOR.submit(_train_in_background, config, generation)
        schedule.pending = future
        schedule.pending_generation = generation
        future.add_done_callback(
            lambda completed, *, state_key=key, selected=config, selected_generation=generation: _training_done(
                state_key, selected, selected_generation, completed
            )
        )
        return _status_locked(config, key, "started", generation_index=generation)


def ensure_fresh_enough(
    workspace: WorkspaceLike, generation_index: int
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    key = runtime.workspace_state_key(config)
    max_lag = max(0, int(config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG))
    generation = int(generation_index)
    latest = latest_completed_generation_index(config.workspace)
    virtual_latest = -1 if latest is None else int(latest)
    if generation - virtual_latest <= max_lag:
        return _status(config, key, "fresh", generation_index=generation)

    waited = wait_for_pending_training(config.workspace)
    latest = latest_completed_generation_index(config.workspace)
    virtual_latest = -1 if latest is None else int(latest)
    if generation - virtual_latest <= max_lag:
        return _status(
            config,
            key,
            "waited",
            generation_index=generation,
            error=waited.error,
        )

    return _train_blocking(config, key, generation)


def reset_workspace_schedule(workspace: WorkspaceLike) -> None:
    """Forget completed scheduler diagnostics for one idle workspace."""

    config = load_config(workspace)
    key = runtime.workspace_state_key(config)
    with _LOCK:
        schedule = _SCHEDULES.get(key)
        if schedule is not None and schedule.pending is not None:
            raise RuntimeError(
                "cannot reset surrogate schedule while training is pending"
            )
        _SCHEDULES.pop(key, None)


def _train_blocking(
    config: LoadedConfig, key: runtime.StateKey, generation_index: int
) -> TrainingScheduleStatus:
    started_at = surrogate_metadata.now_text()
    try:
        state = runtime.train_with_config(
            config,
            generation_index=int(generation_index),
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001 - optimizer may continue without a model.
        surrogate_metadata.record_training_failure(
            config.workspace,
            generation_index=int(generation_index),
            exc=exc,
            started_at=started_at,
        )
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            _schedule_locked(key).last_error = error
        return _status(
            config,
            key,
            "failed",
            generation_index=int(generation_index),
            error=error,
        )

    with _LOCK:
        schedule = _schedule_locked(key)
        schedule.last_completed_generation = int(state.generation_index)
        schedule.last_error = ""
    return _status(
        config,
        key,
        "trained_blocking",
        generation_index=int(generation_index),
    )


def _train_in_background(config: LoadedConfig, generation_index: int):
    return runtime.train_with_config(
        config,
        generation_index=int(generation_index),
        started_at=surrogate_metadata.now_text(),
    )


def _training_done(
    key: runtime.StateKey,
    config: LoadedConfig,
    generation_index: int,
    future: Future,
) -> None:
    try:
        state = future.result()
    except Exception as exc:  # noqa: BLE001 - preserve failure metadata and state.
        surrogate_metadata.record_training_failure(
            config.workspace,
            generation_index=int(generation_index),
            exc=exc,
        )
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            schedule = _schedule_locked(key)
            schedule.last_error = error
            if future is schedule.pending:
                schedule.pending = None
                schedule.pending_generation = None
        return

    with _LOCK:
        schedule = _schedule_locked(key)
        schedule.last_completed_generation = int(state.generation_index)
        schedule.last_error = ""
        if future is schedule.pending:
            schedule.pending = None
            schedule.pending_generation = None


def _schedule_locked(key: runtime.StateKey) -> _WorkspaceSchedule:
    return _SCHEDULES.setdefault(key, _WorkspaceSchedule())


def _refresh_finished_locked(schedule: _WorkspaceSchedule) -> None:
    if schedule.pending is None:
        schedule.pending_generation = None


def _status(
    config: LoadedConfig,
    key: runtime.StateKey,
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    with _LOCK:
        return _status_locked(
            config,
            key,
            action,
            generation_index=generation_index,
            error=error,
        )


def _status_locked(
    config: LoadedConfig,
    key: runtime.StateKey,
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    schedule = _schedule_locked(key)
    state_generation = runtime.latest_state_generation(config.workspace)
    candidates = [
        value
        for value in (state_generation, schedule.last_completed_generation)
        if value is not None
    ]
    return TrainingScheduleStatus(
        action=str(action),
        generation_index=generation_index,
        pending_generation_index=schedule.pending_generation,
        latest_completed_generation_index=max(candidates) if candidates else None,
        error=str(error or schedule.last_error or ""),
    )
