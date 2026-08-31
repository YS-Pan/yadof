"""Independent one-worker freshness scheduler for the PCA/SVD component."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading

from ...config import LoadedConfig, load_config
from ...workspace import WorkspaceContext
from ..training import SurrogateTrainingData, TrainingHandle
from . import runtime
from .settings import DEFAULT_LINEAR_SUBSPACE_SETTINGS, LinearSubspaceSettings


WorkspaceLike = WorkspaceContext | str | Path


@dataclass
class _Schedule:
    pending: TrainingHandle | None = None
    pending_generation: int | None = None
    pending_data_digest: str | None = None
    last_completed_generation: int | None = None
    last_error: str = ""


@dataclass(frozen=True, slots=True)
class TrainingScheduleStatus:
    action: str
    generation_index: int | None = None
    pending_generation_index: int | None = None
    latest_completed_generation_index: int | None = None
    error: str = ""


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
    training_data: SurrogateTrainingData | None = None,
    generation_index: int | None = None,
    error: str = "",
) -> TrainingScheduleStatus:
    key = _key(config, settings)
    with _LOCK:
        item = _schedule(key)
        pending = item.pending_generation
        completed = item.last_completed_generation
        stored_error = item.last_error
    recovered = (
        None
        if training_data is None
        else runtime.latest_state_generation(
            config.workspace,
            training_data,
            _settings=settings,
        )
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
    _training_data: SurrogateTrainingData | None = None,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> TrainingScheduleStatus:
    config = load_config(workspace)
    key = _key(config, _settings)
    with _LOCK:
        item = _schedule(key)
        handle = item.pending
        generation = item.pending_generation
    if handle is None:
        return _status(
            config,
            _settings,
            "idle",
            training_data=_training_data,
        )
    try:
        state = handle.wait()
    except Exception as exc:  # noqa: BLE001 - caller receives the bounded failure.
        error = f"{exc.__class__.__name__}: {exc}"
        with _LOCK:
            item = _schedule(key)
            item.last_error = error
            if item.pending is handle:
                item.pending = None
                item.pending_generation = None
                item.pending_data_digest = None
        try:
            handle.close()
        except Exception:
            pass
        return _status(
            config,
            _settings,
            "failed",
            training_data=_training_data,
            generation_index=generation,
            error=error,
        )
    handle.close()
    with _LOCK:
        item = _schedule(key)
        item.last_completed_generation = state.generation_index
        item.last_error = ""
        if item.pending is handle:
            item.pending = None
            item.pending_generation = None
            item.pending_data_digest = None
    return _status(
        config,
        _settings,
        "completed",
        training_data=_training_data,
        generation_index=generation,
    )


def start_training(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    block: bool = False,
    _config: LoadedConfig | None = None,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _training_data: SurrogateTrainingData | None = None,
    _random_seed: int | None = None,
    _session=None,
    _snapshot=None,
) -> TrainingScheduleStatus:
    del _random_seed
    config = load_config(workspace) if _config is None else _config
    generation = int(generation_index)
    if _training_data is None:
        raise TypeError("pca_svd scheduler requires explicit SurrogateTrainingData")
    if _training_data.sample_count < 1:
        return _status(
            config,
            _settings,
            "skipped_no_data",
            training_data=_training_data,
            generation_index=generation,
        )
    if block:
        wait_for_pending_training(
            config.workspace,
            _training_data=_training_data,
            _settings=_settings,
        )
        state = runtime.fit(
            config.workspace,
            _training_data,
            generation_index=generation,
            _settings=_settings,
            _config=config,
            _session=_session,
            _snapshot=_snapshot,
        )
        key = _key(config, _settings)
        with _LOCK:
            _schedule(key).last_completed_generation = state.generation_index
        return _status(
            config,
            _settings,
            "completed",
            training_data=_training_data,
            generation_index=generation,
        )
    key = _key(config, _settings)
    with _LOCK:
        item = _schedule(key)
        if item.pending is not None:
            return _status(
                config,
                _settings,
                "already_running",
                training_data=_training_data,
                generation_index=generation,
            )
        item.pending = runtime.start_fit(
            config.workspace,
            _training_data,
            generation_index=generation,
            _settings=_settings,
            _config=config,
            _session=_session,
            _snapshot=_snapshot,
        )
        item.pending_generation = generation
        item.pending_data_digest = _training_data.content_digest
    return _status(
        config,
        _settings,
        "started",
        training_data=_training_data,
        generation_index=generation,
    )


def latest_completed_generation_index(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> int | None:
    return _status(
        load_config(workspace),
        _settings,
        "query",
        training_data=training_data,
    ).latest_completed_generation_index


def ensure_fresh_enough(
    workspace: WorkspaceLike,
    generation_index: int,
    *,
    _config: LoadedConfig | None = None,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _training_data: SurrogateTrainingData | None = None,
    _max_training_lag: int | None = None,
    _random_seed: int | None = None,
    _session=None,
    _snapshot=None,
) -> TrainingScheduleStatus:
    config = load_config(workspace) if _config is None else _config
    generation = int(generation_index)
    if _training_data is None:
        raise TypeError("pca_svd freshness requires explicit SurrogateTrainingData")
    if _training_data.sample_count < 1:
        return _status(
            config,
            _settings,
            "skipped_no_data",
            training_data=_training_data,
            generation_index=generation,
        )
    max_lag = max(
        0,
        int(
            config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG
            if _max_training_lag is None
            else _max_training_lag
        ),
    )
    latest = latest_completed_generation_index(
        config.workspace, _training_data, _settings=_settings
    )
    if latest is not None and generation - latest <= max_lag:
        return _status(
            config,
            _settings,
            "fresh",
            training_data=_training_data,
            generation_index=generation,
        )
    wait_for_pending_training(
        config.workspace,
        _training_data=_training_data,
        _settings=_settings,
    )
    latest = latest_completed_generation_index(
        config.workspace, _training_data, _settings=_settings
    )
    if latest is not None and generation - latest <= max_lag:
        return _status(
            config,
            _settings,
            "waited",
            training_data=_training_data,
            generation_index=generation,
        )
    return start_training(
        config.workspace,
        generation,
        block=True,
        _config=config,
        _settings=_settings,
        _training_data=_training_data,
        _random_seed=_random_seed,
        _session=_session,
        _snapshot=_snapshot,
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
    for key, handle in selected:
        if handle is None:
            continue
        try:
            completed.append(handle.finish().generation_index)
        except Exception as exc:  # noqa: BLE001 - deactivation reports every failure.
            errors.append(f"{exc.__class__.__name__}: {exc}")
    with _LOCK:
        for key, _handle in selected:
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
