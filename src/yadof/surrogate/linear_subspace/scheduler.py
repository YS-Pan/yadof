"""Independent one-worker freshness scheduler for the PCA/SVD component."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import threading

from ...config import LoadedConfig, load_config
from ...task_snapshot import create_generation_snapshot
from ...workspace import WorkspaceContext
from . import runtime
from .settings import DEFAULT_LINEAR_SUBSPACE_SETTINGS, LinearSubspaceSettings


WorkspaceLike = WorkspaceContext | str | Path


@dataclass
class _Schedule:
    pending: Future | None = None
    pending_generation: int | None = None
    last_completed_generation: int | None = None
    last_error: str = ""


@dataclass(frozen=True, slots=True)
class TrainingScheduleStatus:
    action: str
    generation_index: int | None = None
    pending_generation_index: int | None = None
    latest_completed_generation_index: int | None = None
    error: str = ""


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yadof-pca-svd")
_LOCK = threading.RLock()
_SCHEDULES: dict[runtime.StateKey, _Schedule] = {}


def _key(config: LoadedConfig, settings: LinearSubspaceSettings):
    return runtime.workspace_state_key(config, settings=settings)


def _schedule(key) -> _Schedule:
    return _SCHEDULES.setdefault(key, _Schedule())


def _status(
    config: LoadedConfig,
    settings: LinearSubspaceSettings,
    action: str,
    *,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    key = _key(config, settings)
    with _LOCK:
        item = _schedule(key)
        pending = item.pending_generation
        completed = item.last_completed_generation
        stored_error = item.last_error
    recovered = runtime.latest_state_generation(
        config.workspace, _settings=settings
    )
    values = tuple(value for value in (completed, recovered) if value is not None)
    return TrainingScheduleStatus(
        action=action,
        generation_index=generation_index,
        pending_generation_index=pending,
        latest_completed_generation_index=max(values) if values else None,
        error=error or stored_error,
    )


def wait_for_pending_training(
    workspace: WorkspaceLike,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    key = _key(config, _settings)
    with _LOCK:
        item = _schedule(key)
        future = item.pending
        generation = item.pending_generation
    if future is None:
        return _status(config, _settings, "idle")
    try:
        state = future.result()
    except Exception as exc:  # noqa: BLE001 - caller receives the bounded failure.
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            item = _schedule(key)
            item.last_error = error
            if item.pending is future:
                item.pending = None
                item.pending_generation = None
        return _status(
            config,
            _settings,
            "failed",
            generation_index=generation,
            error=error,
        )
    with _LOCK:
        item = _schedule(key)
        item.last_completed_generation = state.generation_index
        item.last_error = ""
        if item.pending is future:
            item.pending = None
            item.pending_generation = None
    return _status(
        config,
        _settings,
        "completed",
        generation_index=generation,
    )


def _train(
    config: LoadedConfig,
    generation: int,
    settings: LinearSubspaceSettings,
    training_data,
    random_seed: int | None,
):
    return runtime.train_with_config(
        config,
        generation_index=generation,
        training_data=training_data,
        settings=settings,
        random_seed=random_seed,
    )


def start_training(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    block: bool = False,
    _config: LoadedConfig | None = None,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _training_data=None,
    _random_seed: int | None = None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
    generation = int(generation_index)
    if block:
        wait_for_pending_training(config.workspace, _settings=_settings)
        state = _train(
            config, generation, _settings, _training_data, _random_seed
        )
        key = _key(config, _settings)
        with _LOCK:
            _schedule(key).last_completed_generation = state.generation_index
        return _status(
            config, _settings, "completed", generation_index=generation
        )
    key = _key(config, _settings)
    with _LOCK:
        item = _schedule(key)
        if item.pending is not None and not item.pending.done():
            return _status(
                config, _settings, "already_running", generation_index=generation
            )
        owned = create_generation_snapshot(config)
        item.pending = _EXECUTOR.submit(
            _train,
            owned.config,
            generation,
            _settings,
            _training_data,
            _random_seed,
        )
        item.pending_generation = generation
        item.pending.add_done_callback(
            lambda _completed, snapshot=owned: snapshot.close()
        )
    return _status(config, _settings, "started", generation_index=generation)


def latest_completed_generation_index(
    workspace: WorkspaceLike,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> int | None:
    return _status(load_config(workspace), _settings, "query").latest_completed_generation_index


def ensure_fresh_enough(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    _config: LoadedConfig | None = None,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _training_data=None,
    _max_training_lag: int | None = None,
    _random_seed: int | None = None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
    generation = int(generation_index)
    max_lag = max(
        0,
        int(
            config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG
            if _max_training_lag is None
            else _max_training_lag
        ),
    )
    latest = latest_completed_generation_index(
        config.workspace, _settings=_settings
    )
    if latest is not None and generation - latest <= max_lag:
        return _status(config, _settings, "fresh", generation_index=generation)
    wait_for_pending_training(config.workspace, _settings=_settings)
    latest = latest_completed_generation_index(
        config.workspace, _settings=_settings
    )
    if latest is not None and generation - latest <= max_lag:
        return _status(config, _settings, "waited", generation_index=generation)
    return start_training(
        config.workspace,
        generation,
        block=True,
        _config=config,
        _settings=_settings,
        _training_data=_training_data,
        _random_seed=_random_seed,
    )


def deactivate_workspace(
    workspace: WorkspaceLike,
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    root = str(config.workspace.root)
    with _LOCK:
        selected = tuple((key, value.pending) for key, value in _SCHEDULES.items() if key[0] == root)
    errors = []
    completed = []
    for key, future in selected:
        if future is None:
            continue
        try:
            completed.append(future.result().generation_index)
        except Exception as exc:  # noqa: BLE001 - deactivation reports every failure.
            errors.append(f"{exc.__class__.__name__}: {exc}")
    with _LOCK:
        for key, _future in selected:
            _SCHEDULES.pop(key, None)
    runtime.reset_workspace_state(config.workspace)
    return TrainingScheduleStatus(
        action="deactivated" if not errors else "deactivated_with_errors",
        latest_completed_generation_index=max(completed) if completed else None,
        error="; ".join(errors),
    )


__all__ = [
    "TrainingScheduleStatus",
    "deactivate_workspace",
    "ensure_fresh_enough",
    "latest_completed_generation_index",
    "start_training",
    "wait_for_pending_training",
]
