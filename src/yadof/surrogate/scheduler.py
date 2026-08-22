from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import threading

from ..config import LoadedConfig, load_config
from ..task_snapshot import create_generation_snapshot
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
    usable = runtime._is_usable_state(state)
    with _LOCK:
        schedule = _schedule_locked(key)
        if usable:
            schedule.last_completed_generation = int(state.generation_index)
        schedule.last_error = ""
        if future is schedule.pending:
            schedule.pending = None
            schedule.pending_generation = None
    return _status(
        config,
        key,
        "completed" if usable else "skipped_not_trainable",
        generation_index=pending_generation,
    )


def start_training(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    block: bool = False,
    _config: LoadedConfig | None = None,
    _training_data=None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
    key = runtime.workspace_state_key(config)
    generation = int(generation_index)

    if block:
        wait_for_pending_training(config.workspace)
        return _train_blocking(
            config, key, generation, training_data=_training_data
        )

    with _LOCK:
        schedule = _schedule_locked(key)
        _refresh_finished_locked(schedule)
        if schedule.pending is not None and not schedule.pending.done():
            return _status_locked(
                config, key, "already_running", generation_index=generation
            )
        owned_snapshot = create_generation_snapshot(config)
        future = _EXECUTOR.submit(
            _train_in_background,
            owned_snapshot.config,
            generation,
            _training_data,
        )
        schedule.pending = future
        schedule.pending_generation = generation
        future.add_done_callback(
            lambda completed, *, state_key=key, selected=config, selected_generation=generation, owned=owned_snapshot: _training_done_owned(
                state_key, selected, selected_generation, completed, owned
            )
        )
        return _status_locked(config, key, "started", generation_index=generation)


def ensure_fresh_enough(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    _config: LoadedConfig | None = None,
    _training_data=None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
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

    return _train_blocking(
        config, key, generation, training_data=_training_data
    )


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


def deactivate_workspace(workspace: WorkspaceLike) -> TrainingScheduleStatus:
    """Finish and release one active strategy's in-memory surrogate state.

    Published checkpoint artifacts are deliberately retained so that selecting
    the same semantic strategy later can recover its component state.
    """

    config = load_config(workspace)
    key = runtime.workspace_state_key(config)
    status = wait_for_pending_training(config.workspace)
    with _LOCK:
        _SCHEDULES.pop(key, None)
    runtime.reset_workspace_state(config.workspace)
    return TrainingScheduleStatus(
        action="deactivated",
        generation_index=status.generation_index,
        pending_generation_index=None,
        latest_completed_generation_index=status.latest_completed_generation_index,
        error=status.error,
    )


def _train_blocking(
    config: LoadedConfig,
    key: runtime.StateKey,
    generation_index: int,
    *,
    training_data=None,
) -> TrainingScheduleStatus:
    started_at = surrogate_metadata.now_text()
    try:
        state = runtime.train_with_config(
            config,
            generation_index=int(generation_index),
            started_at=started_at,
            training_data=training_data,
        )
    except Exception as exc:  # noqa: BLE001 - optimizer may continue without a model.
        surrogate_metadata.record_training_failure(
            config.workspace,
            generation_index=int(generation_index),
            exc=exc,
            started_at=started_at,
            strategy_signature=runtime.strategy_signature_for_workspace(
                config.workspace
            ),
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

    usable = runtime._is_usable_state(state)
    with _LOCK:
        schedule = _schedule_locked(key)
        if usable:
            schedule.last_completed_generation = int(state.generation_index)
        schedule.last_error = ""
    return _status(
        config,
        key,
        "trained_blocking" if usable else "skipped_not_trainable",
        generation_index=int(generation_index),
    )


def _train_in_background(
    config: LoadedConfig, generation_index: int, training_data=None
):
    return runtime.train_with_config(
        config,
        generation_index=int(generation_index),
        started_at=surrogate_metadata.now_text(),
        training_data=training_data,
    )


def _training_done_owned(
    key: runtime.StateKey,
    config: LoadedConfig,
    generation_index: int,
    future: Future,
    owned_snapshot,
) -> None:
    try:
        _training_done(key, config, generation_index, future)
    finally:
        owned_snapshot.close()


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
            strategy_signature=runtime.strategy_signature_for_workspace(
                config.workspace
            ),
        )
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            schedule = _SCHEDULES.get(key)
            if schedule is None:
                return
            schedule.last_error = error
            if future is schedule.pending:
                schedule.pending = None
                schedule.pending_generation = None
        return

    usable = runtime._is_usable_state(state)
    with _LOCK:
        schedule = _SCHEDULES.get(key)
        if schedule is None:
            return
        if usable:
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
