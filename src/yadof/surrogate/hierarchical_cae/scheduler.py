from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import threading

from ...config import LoadedConfig, load_config
from ...task_snapshot import create_generation_snapshot
from ...workspace import WorkspaceContext
from . import metadata as surrogate_metadata
from . import runtime


WorkspaceLike = WorkspaceContext | str | Path


@dataclass
class _WorkspaceSchedule:
    pending: Future | None = None
    pending_generation: int | None = None
    last_completed_generation: int | None = None
    last_error: str = ""


@dataclass(frozen=True)
class TrainingScheduleStatus:
    action: str
    generation_index: int | None = None
    pending_generation_index: int | None = None
    latest_completed_generation_index: int | None = None
    error: str = ""


_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="yadof-hierarchical-cae"
)
_LOCK = threading.RLock()
_SCHEDULES: dict[runtime.StateKey, _WorkspaceSchedule] = {}


def has_trained_state(workspace: WorkspaceLike, *, _component) -> bool:
    return runtime.has_trained_state(workspace, component=_component)


def latest_completed_generation_index(
    workspace: WorkspaceLike, *, _component
) -> int | None:
    config = load_config(workspace)
    key = runtime.workspace_state_key(config, component=_component)
    state_generation = runtime.latest_state_generation(
        config.workspace, component=_component
    )
    with _LOCK:
        schedule = _SCHEDULES.get(key)
        values = tuple(
            value
            for value in (
                state_generation,
                None if schedule is None else schedule.last_completed_generation,
            )
            if value is not None
        )
    return max(values) if values else None


def wait_for_pending_training(
    workspace: WorkspaceLike, *, _component
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    key = runtime.workspace_state_key(config, component=_component)
    with _LOCK:
        schedule = _schedule_locked(key)
        future = schedule.pending
        pending_generation = schedule.pending_generation
    if future is None:
        return _status(config, key, _component, "idle")
    try:
        state = future.result()
    except Exception as exc:  # noqa: BLE001 - real evaluation remains available.
        return _status(
            config,
            key,
            _component,
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
        _component,
        "completed" if usable else "skipped_not_trainable",
        generation_index=pending_generation,
    )


def start_training(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    block: bool = False,
    _config: LoadedConfig | None = None,
    _component,
    _training_data=None,
    _random_seed: int | None = None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
    key = runtime.workspace_state_key(config, component=_component)
    generation = int(generation_index)
    if block:
        wait_for_pending_training(config.workspace, _component=_component)
        return _train_blocking(
            config,
            key,
            generation,
            component=_component,
            random_seed=_random_seed,
            training_data=_training_data,
        )

    with _LOCK:
        schedule = _schedule_locked(key)
        if schedule.pending is not None and not schedule.pending.done():
            return _status_locked(
                config,
                key,
                _component,
                "already_running",
                generation_index=generation,
            )
        owned_snapshot = create_generation_snapshot(config)
        future = _EXECUTOR.submit(
            _train_in_background,
            owned_snapshot.config,
            generation,
            _component,
            _training_data,
            _random_seed,
        )
        schedule.pending = future
        schedule.pending_generation = generation
        future.add_done_callback(
            lambda completed, *, state_key=key, selected=config, selected_generation=generation, selected_component=_component, owned=owned_snapshot: _training_done_owned(
                state_key,
                selected,
                selected_generation,
                selected_component,
                completed,
                owned,
            )
        )
        return _status_locked(
            config, key, _component, "started", generation_index=generation
        )


def ensure_fresh_enough(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    _config: LoadedConfig | None = None,
    _component,
    _training_data=None,
    _max_training_lag: int | None = None,
    _random_seed: int | None = None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
    key = runtime.workspace_state_key(config, component=_component)
    max_lag = max(
        0,
        int(
            config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG
            if _max_training_lag is None
            else _max_training_lag
        ),
    )
    generation = int(generation_index)
    latest = latest_completed_generation_index(
        config.workspace, _component=_component
    )
    virtual_latest = -1 if latest is None else int(latest)
    if generation - virtual_latest <= max_lag:
        return _status(
            config, key, _component, "fresh", generation_index=generation
        )

    waited = wait_for_pending_training(
        config.workspace, _component=_component
    )
    latest = latest_completed_generation_index(
        config.workspace, _component=_component
    )
    virtual_latest = -1 if latest is None else int(latest)
    if generation - virtual_latest <= max_lag:
        return _status(
            config,
            key,
            _component,
            "waited",
            generation_index=generation,
            error=waited.error,
        )
    return _train_blocking(
        config,
        key,
        generation,
        component=_component,
        random_seed=_random_seed,
        training_data=_training_data,
    )


def reset_workspace_schedule(
    workspace: WorkspaceLike, *, _component=None
) -> None:
    config = load_config(workspace)
    root = str(config.workspace.root)
    with _LOCK:
        keys = (
            (runtime.workspace_state_key(config, component=_component),)
            if _component is not None
            else tuple(key for key in _SCHEDULES if key[0] == root)
        )
        for key in keys:
            schedule = _SCHEDULES.get(key)
            if schedule is not None and schedule.pending is not None:
                raise RuntimeError(
                    "cannot reset hierarchical CAE schedule while training is pending"
                )
        for key in keys:
            _SCHEDULES.pop(key, None)


def deactivate_workspace(
    workspace: WorkspaceLike, *, _component=None
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    root = str(config.workspace.root)
    errors: list[str] = []
    completed: list[int] = []
    if _component is not None:
        status = wait_for_pending_training(
            config.workspace, _component=_component
        )
        if status.error:
            errors.append(status.error)
        if status.latest_completed_generation_index is not None:
            completed.append(status.latest_completed_generation_index)
        keys = (runtime.workspace_state_key(config, component=_component),)
    else:
        with _LOCK:
            scheduled = tuple(
                (key, schedule.pending, schedule.pending_generation)
                for key, schedule in _SCHEDULES.items()
                if key[0] == root
            )
        for _key, future, generation in scheduled:
            if future is None:
                continue
            try:
                state = future.result()
                if runtime._is_usable_state(state):
                    completed.append(int(state.generation_index))
            except Exception as exc:  # noqa: BLE001 - report while deactivating.
                errors.append(
                    f"generation {generation}: {exc.__class__.__name__}: {exc}"
                )
        keys = tuple(key for key in _SCHEDULES if key[0] == root)
    with _LOCK:
        for key in keys:
            _SCHEDULES.pop(key, None)
    runtime.reset_workspace_state(config.workspace, component=_component)
    return TrainingScheduleStatus(
        action="deactivated",
        latest_completed_generation_index=max(completed) if completed else None,
        error="; ".join(errors),
    )


def _train_blocking(
    config: LoadedConfig,
    key: runtime.StateKey,
    generation_index: int,
    *,
    component,
    random_seed: int | None,
    training_data=None,
) -> TrainingScheduleStatus:
    started_at = surrogate_metadata.now_text()
    try:
        state = runtime.train_with_config(
            config,
            generation_index=int(generation_index),
            component=component,
            started_at=started_at,
            training_data=training_data,
            random_seed=random_seed,
        )
    except Exception as exc:  # noqa: BLE001 - optimizer may use real evaluation.
        surrogate_metadata.record_training_failure(
            config.workspace,
            generation_index=int(generation_index),
            exc=exc,
            started_at=started_at,
            strategy_signature=runtime.strategy_signature_for_workspace(
                config.workspace, component=component
            ),
        )
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            _schedule_locked(key).last_error = error
        return _status(
            config,
            key,
            component,
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
        component,
        "trained_blocking" if usable else "skipped_not_trainable",
        generation_index=int(generation_index),
    )


def _train_in_background(
    config: LoadedConfig,
    generation_index: int,
    component,
    training_data,
    random_seed: int | None,
):
    return runtime.train_with_config(
        config,
        generation_index=int(generation_index),
        component=component,
        started_at=surrogate_metadata.now_text(),
        training_data=training_data,
        random_seed=random_seed,
    )


def _training_done_owned(
    key: runtime.StateKey,
    config: LoadedConfig,
    generation_index: int,
    component,
    future: Future,
    owned_snapshot,
) -> None:
    try:
        _training_done(key, config, generation_index, component, future)
    finally:
        owned_snapshot.close()


def _training_done(
    key: runtime.StateKey,
    config: LoadedConfig,
    generation_index: int,
    component,
    future: Future,
) -> None:
    try:
        state = future.result()
    except Exception as exc:  # noqa: BLE001 - preserve failure diagnostics.
        surrogate_metadata.record_training_failure(
            config.workspace,
            generation_index=int(generation_index),
            exc=exc,
            strategy_signature=runtime.strategy_signature_for_workspace(
                config.workspace, component=component
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


def _status(
    config: LoadedConfig,
    key: runtime.StateKey,
    component,
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    with _LOCK:
        return _status_locked(
            config,
            key,
            component,
            action,
            generation_index=generation_index,
            error=error,
        )


def _status_locked(
    config: LoadedConfig,
    key: runtime.StateKey,
    component,
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    schedule = _schedule_locked(key)
    state_generation = runtime.latest_state_generation(
        config.workspace, component=component
    )
    values = tuple(
        value
        for value in (state_generation, schedule.last_completed_generation)
        if value is not None
    )
    return TrainingScheduleStatus(
        action=str(action),
        generation_index=generation_index,
        pending_generation_index=schedule.pending_generation,
        latest_completed_generation_index=max(values) if values else None,
        error=str(error or schedule.last_error or ""),
    )


__all__ = [
    "TrainingScheduleStatus",
    "deactivate_workspace",
    "ensure_fresh_enough",
    "has_trained_state",
    "latest_completed_generation_index",
    "reset_workspace_schedule",
    "start_training",
    "wait_for_pending_training",
]
